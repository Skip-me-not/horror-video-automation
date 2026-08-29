from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.caption_renderer import write_ass
from src.captions import Caption, parse_vtt, slice_captions
from src.compositor import compose
from src.config_loader import Settings, load_settings
from src.hook_builder import build_hook
from src.horror_scorer import HorrorScorer
from src.reference_query_builder import build_reference_queries
from src.shot_planner import build_edit_plan, validate_edit_plan
from src.story_segment_builder import build_story_segment
from src.utils import ffprobe
from src.video_transform import transform_source
from src.youtube_search import filter_results


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


@pytest.mark.skipif(shutil.which("ffmpeg") is None or FFPROBE is None,
                    reason="FFmpeg is required")
def test_phase_one_transform_and_continuous_audio_compositor(tmp_path):
    source = tmp_path / "source.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=240:sample_rate=48000", "-t", "6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
    ], check=True, capture_output=True)
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
            "broll_ratio": 0.0, "source_audio_continuous": True,
            "segments": [{"type": "hook", "start": 0.0, "end": 1.0, "text": hook["text"]},
                         {"type": "podcast", "start": 1.0, "end": 4.0, "crop_variant": 1.05}]}
    final = compose(vertical, plan, captions, tmp_path / "short.mp4", tmp_path / "work", settings)
    payload = ffprobe(final, FFPROBE)
    streams = {item["codec_type"]: item for item in payload["streams"]}
    assert streams["video"]["codec_name"] == "h264"
    assert streams["audio"]["codec_name"] == "aac"
    assert abs(float(streams["video"].get("duration", 4)) - float(streams["audio"].get("duration", 4))) < 0.2
