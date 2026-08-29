from __future__ import annotations

import json
import shutil
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.caption_renderer import write_ass
from src.captions import Caption, parse_vtt, slice_captions
from src.compositor import compose
from src.config_loader import Settings, load_settings
from src.downloader import download_selected_video
from src.history import HistoryStore
from src.hook_builder import build_hook
from src.horror_scorer import HorrorScorer
from src.reference_query_builder import build_reference_queries
from src.shot_planner import attach_stock_assets, build_edit_plan, validate_edit_plan
from src.story_segment_builder import build_story_segment
from src.utils import ffprobe
from src.video_transform import transform_source
from src.youtube_search import filter_results
from src.youtube_search import SourceResult
import src.compositor as compositor_module
import src.main as main_module


LOCAL_FFPROBE = Path(__file__).resolve().parents[1] / ".test-tools" / "ffprobe.exe"
FFPROBE = shutil.which("ffprobe") or (str(LOCAL_FFPROBE) if LOCAL_FFPROBE.is_file() else None)


def test_settings_and_random_metadata_filter(repo_root):
    settings = load_settings(repo_root)
    assert settings.source_speed == 1.10
    settings = Settings(root=repo_root)
    entries = [
        {"id": "allowed", "duration": 900, "title": "Reusable", "live_status": "not_live",
         "license": "Creative Commons Attribution license (reuse allowed)"},
        {"id": "standard", "duration": 900, "title": "Standard", "live_status": "not_live",
         "license": "Standard YouTube License"},
        {"id": "short", "duration": 40, "title": "Short", "live_status": "not_live",
         "license": "Creative Commons"},
        {"id": "live", "duration": 900, "title": "Live", "live_status": "is_live",
         "license": "Creative Commons"},
    ]
    results = filter_results(entries, settings, set())
    assert [item.video_id for item in results] == ["allowed", "standard"]


def test_vtt_scoring_segment_hook_and_queries(tmp_path, repo_root):
    vtt = tmp_path / "source.vtt"
    lines = ["WEBVTT", ""]
    for index in range(40):
        start = index * 5
        text = ("I heard footsteps in the dark hallway and I was alone."
                if index == 18 else "We kept talking about what happened that night.")
        if index == 30:
            text = "I ran outside and never went back to that house."
        lines.extend([f"00:{start // 60:02d}:{start % 60:02d}.000 --> 00:{(start + 4) // 60:02d}:{(start + 4) % 60:02d}.000",
                      text, ""])
    vtt.write_text("\n".join(lines), encoding="utf-8")
    captions = parse_vtt(vtt)
    triggers = json.loads((repo_root / "config" / "horror_triggers.json").read_text())
    scoring = json.loads((repo_root / "config" / "scoring.json").read_text())
    moments = HorrorScorer(triggers, scoring).score_all(captions)
    assert moments[0].score >= scoring["minimum_anchor_score"]
    candidates = [{"anchor": moments[0].caption.__dict__, "score": moments[0].score,
                   "categories": list(moments[0].categories), "matches": list(moments[0].matches)}]
    story = build_story_segment(captions, candidates, [], 220, 1.1, 65, 110, 175,
                                scoring["ending_terms"])
    assert 65 <= story["final_duration"] <= 150
    relative = slice_captions(captions, story["start"], story["end"], 1.1)
    assert relative and relative[0].start >= 0
    hook = build_hook(story["transcript"], candidates[0]["matches"])
    assert 2 <= hook["duration"] <= 5
    queries = build_reference_queries(relative, {"hallway": ["dark hallway"]})
    assert queries and queries[0]["query"] == "dark hallway"


def test_edit_plan_is_contiguous_and_limits_static_speaker():
    hook = {"text": "He thought he was alone.", "duration": 3.0}
    events = [{"time": time, "keyword": f"event-{index}", "query": f"query-{index}"}
              for index, time in enumerate((14, 30, 46, 62, 78))]
    assets = {f"query-{index}": {"media_type": "video" if index % 2 == 0 else "image",
                                 "local_path": f"asset-{index}.mp4"}
              for index in range(5)}
    plan = build_edit_plan(100, 1.1, True, hook, events, assets, 0.25, 2, 6, 9)
    validate_edit_plan(plan)
    podcast = [item for item in plan["segments"] if item["type"] == "podcast"]
    assert all(item["end"] - item["start"] <= 9.001 for item in podcast)
    assert 0.15 <= plan["broll_ratio"] <= 0.35
    assert plan["source_audio_continuous"] is True
    draft = build_edit_plan(100, 1.1, True, hook, events, {}, 0.25, 2.5, 4.5, 9, 5, 7)
    assert 1 <= draft["planned_broll_count"] <= 7
    assert any(item["type"] == "planned_broll" for item in draft["segments"])
    fallback = attach_stock_assets(draft, {})
    assert all(item["type"] != "planned_broll" for item in fallback["segments"])
    assert fallback["stock_asset_count"] == 0
    validate_edit_plan(fallback)


def test_processed_source_exits_before_caption_or_media_download(tmp_path, monkeypatch):
    history = HistoryStore(tmp_path / "history.json")
    history.append({"source_video_id": "used"})
    monkeypatch.setattr(main_module, "download_captions",
                        lambda *_args, **_kwargs: pytest.fail("captions must not download"))
    result = SourceResult("used", "https://example.invalid/watch?v=used", "Used", 900,
                          "Channel", "channel", "not_live", "")
    args = SimpleNamespace(force_reprocess=False, start=None)
    with pytest.raises(RuntimeError, match="EARLY_SKIP_ALREADY_PROCESSED"):
        main_module._remote_attempt(result, tmp_path / "attempt", args, Settings(root=tmp_path), 110,
                                    {}, {}, history, main_module.PerformanceTracker(), tmp_path / "log.txt")


def test_caption_failure_continues_with_audio_only_fallback(tmp_path, monkeypatch):
    result = SourceResult("fresh", "https://example.invalid/watch?v=fresh", "Fresh", 900,
                          "Channel", "channel", "not_live", "")
    monkeypatch.setattr(main_module, "download_captions", lambda *_args, **_kwargs:
                        (_ for _ in ()).throw(RuntimeError("HTTP 429")))

    def fake_audio(_url, directory):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "audio.opus"
        path.write_bytes(b"audio")
        return path

    selected = {"start": 100.0, "end": 171.5, "source_duration": 71.5,
                "final_duration": 65.0, "transcript": "", "score": 8.0,
                "has_payoff_signal": False, "selection_mode": "audio-only"}
    monkeypatch.setattr(main_module, "download_audio", fake_audio)
    monkeypatch.setattr(main_module, "_audio_only_story", lambda *_args, **_kwargs: selected.copy())

    def fake_range(_url, directory, _start, _end, _settings):
        directory.mkdir(parents=True, exist_ok=True)
        video = directory / "selected.mp4"
        video.write_bytes(b"selected-video")
        return {"video": video, "info": {}, "media_start": 97.0,
                "range_downloaded": True, "range_error": ""}

    monkeypatch.setattr(main_module, "download_selected_video", fake_range)
    log = tmp_path / "processing.log"
    payload = main_module._remote_attempt(
        result, tmp_path / "attempt", SimpleNamespace(force_reprocess=False, start=None),
        Settings(root=tmp_path), 110, {}, {}, HistoryStore(tmp_path / "history.json"),
        main_module.PerformanceTracker(), log,
    )
    assert payload["selected"]["selection_mode"] == "audio-only"
    assert "CAPTION_RETRIEVAL_FAILED_AUDIO_FALLBACK" in log.read_text(encoding="utf-8")


def test_range_download_requests_only_selected_section(tmp_path, monkeypatch):
    captured = {}

    class FakeYDL:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download):
            assert download is True
            (tmp_path / "selected.mp4").write_bytes(b"range-media")
            return {"id": "video", "duration": 900}

    yt_dlp = types.ModuleType("yt_dlp")
    yt_dlp.YoutubeDL = FakeYDL
    yt_dlp_utils = types.ModuleType("yt_dlp.utils")
    yt_dlp_utils.download_range_func = lambda _chapters, ranges: {"ranges": ranges}
    monkeypatch.setitem(sys.modules, "yt_dlp", yt_dlp)
    monkeypatch.setitem(sys.modules, "yt_dlp.utils", yt_dlp_utils)
    payload = download_selected_video("https://example.invalid/video", tmp_path, 10, 80,
                                      Settings(root=tmp_path, range_download_padding_seconds=3))
    assert captured["download_ranges"] == {"ranges": [(7, 83)]}
    assert payload["range_downloaded"] is True
    assert payload["media_start"] == 7


def test_audio_only_fallback_uses_energy_change(tmp_path, monkeypatch):
    audio = tmp_path / "audio.opus"
    audio.write_bytes(b"audio")
    monkeypatch.setattr(main_module, "energy_changes", lambda _path: [{"time": 300, "delta_db": 8.5}])
    story = main_module._audio_only_story(audio, 900, Settings(root=tmp_path), 110)
    assert story["selection_mode"] == "audio-only"
    assert 65 <= story["final_duration"] <= 175


def test_compositor_launches_one_final_encode(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    captions = tmp_path / "captions.ass"
    destination = tmp_path / "short.mp4"
    source.write_bytes(b"source")
    captions.write_text("[Script Info]\n", encoding="utf-8")
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        destination.write_bytes(b"final-video")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(compositor_module, "run", fake_run)
    plan = {"final_duration": 65.0, "source_speed": 1.1,
            "segments": [{"type": "hook", "start": 0.0, "end": 3.0}],
            "source_audio_continuous": True}
    compose(source, plan, captions, destination, tmp_path / "render", Settings(root=tmp_path),
            source_duration=71.5)
    assert len(calls) == 1
    assert "-filter_complex" in calls[0]
    assert calls[0].count("-c:v") == 1


def test_workflow_has_upload_cleanup_and_pinned_runner(repo_root):
    workflow = (repo_root / ".github" / "workflows" / "horror-short-generator.yml").read_text()
    assert "runs-on: ubuntu-24.04" in workflow
    assert "actions/cache@v4" not in workflow
    assert "command -v ffmpeg" in workflow
    assert "timeout-minutes: 45" in workflow
    assert "pip install --upgrade yt-dlp" not in workflow
    assert "Upload finished video to YouTube as public" in workflow
    assert 'startswith("ffmpeg-")' in workflow
    assert 'startswith("setup-python-")' in workflow
    assert "gh cache delete --all" not in workflow
    assert "rm -f output/short.mp4" in workflow


@pytest.mark.skipif(shutil.which("ffmpeg") is None or FFPROBE is None,
                    reason="FFmpeg is required")
def test_phase_one_transform_and_continuous_audio_compositor(tmp_path):
    source = tmp_path / "source.mp4"
    reference = tmp_path / "reference.jpg"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=240:sample_rate=48000", "-t", "6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
    ], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x182033:s=320x240",
                    "-frames:v", "1", "-c:v", "mjpeg", str(reference)],
                   check=True, capture_output=True)
    settings = Settings(root=tmp_path, output_width=360, output_height=640, fps=30,
                        source_speed=1.1, crf=25)
    vertical = tmp_path / "vertical.mp4"
    transform_source(source, vertical, 0, 5.5, settings)
    transformed_probe = ffprobe(vertical, FFPROBE)
    video = next(item for item in transformed_probe["streams"] if item["codec_type"] == "video")
    assert (video["width"], video["height"]) == (360, 640)
    assert 4.8 <= float(transformed_probe["format"]["duration"]) <= 5.2

    hook = {"text": "He thought he was alone.", "duration": 1.0}
    captions = write_ass(tmp_path / "captions.ass", [Caption(0, 4, "someone was behind the door")],
                         hook, {"someone", "behind", "door"}, 360, 640)
    ass_text = captions.read_text(encoding="utf-8")
    assert r"\N" in ass_text
    assert r"{\1c&H3030E3&}SOMEONE" in ass_text
    assert r"{\1c&H3030E3&}WAS" not in ass_text
    plan = {"final_duration": 4.0, "source_speed": 1.1, "horizontal_flip": True,
            "broll_ratio": 0.25, "source_audio_continuous": True,
            "segments": [{"type": "hook", "start": 0.0, "end": 1.0, "text": hook["text"]},
                         {"type": "podcast", "start": 1.0, "end": 2.0, "crop_variant": 1.05},
                         {"type": "reference_image", "start": 2.0, "end": 3.0,
                          "asset": {"local_path": str(reference), "media_type": "image"}},
                         {"type": "podcast", "start": 3.0, "end": 4.0, "crop_variant": 1.0}]}
    final = compose(vertical, plan, captions, tmp_path / "short.mp4", tmp_path / "work", settings)
    payload = ffprobe(final, FFPROBE)
    streams = {item["codec_type"]: item for item in payload["streams"]}
    assert streams["video"]["codec_name"] == "h264"
    assert streams["audio"]["codec_name"] == "aac"
    assert abs(float(streams["video"].get("duration", 4)) - float(streams["audio"].get("duration", 4))) < 0.2
