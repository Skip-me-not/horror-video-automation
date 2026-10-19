import json
from pathlib import Path

import pytest

from scripts import content_quality as quality
from scripts.merge_reddit_state import merge_states
from scripts.render_idol_short import candidate_idols, reddit_direct_variants


def config():
    return quality.load_quality_config()


def post(post_id="one", *, score=800, created_utc=1_800_000_000):
    return {
        "id": post_id, "permalink": f"/r/kpop/comments/{post_id}/title/",
        "video_url": f"https://v.redd.it/{post_id}/DASH_720.mp4",
        "score": score, "score_available": score is not None,
        "num_comments": 80, "created_utc": created_utc, "views": None,
    }


def media(**overrides):
    return {
        "duration": 30.0, "width": 1080, "height": 1920, "fps": 30.0,
        "bitrate": 2_000_000, "file_size": 2_000_000,
        "aspect_ratio": 1080 / 1920, "has_audio": False,
        **overrides,
    }


def patch_frames(monkeypatch):
    monkeypatch.setattr(quality, "sample_hashes", lambda *_: (["0101010101010101", "0202020202020202",
                                                         "0303030303030303", "0404040404040404"], 100.0, 0.5))
    monkeypatch.setattr(quality, "file_sha256", lambda *_: "sha-one")


def test_source_rejects_low_resolution_before_upscaling(monkeypatch, tmp_path):
    monkeypatch.setattr(quality, "probe_media", lambda *_: media(width=480))
    monkeypatch.setattr(quality, "sample_hashes", lambda *_: pytest.fail("should not sample rejected source"))
    record = quality.inspect_source(tmp_path / "clip.mp4", post(), [], config())
    assert not record["accepted"]
    assert "width 480 below 720" in record["reasons"]


def test_source_score_redistributes_missing_engagement(monkeypatch, tmp_path):
    monkeypatch.setattr(quality, "probe_media", lambda *_: media())
    patch_frames(monkeypatch)
    unknown = post(score=None)
    record = quality.inspect_source(tmp_path / "clip.mp4", unknown, [], config(), now=1_800_000_000)
    assert record["upvotes"] is None
    assert record["factors"]["engagement"] is None
    assert record["score"] >= 60
    assert record["accepted"]


def test_exact_and_near_duplicate_recent_sources_are_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(quality, "probe_media", lambda *_: media())
    patch_frames(monkeypatch)
    fresh = quality.inspect_source(tmp_path / "clip.mp4", post(), [], config(), now=1_800_000_000)
    exact = quality.inspect_source(tmp_path / "clip.mp4", post(), [fresh], config(), now=1_800_000_000)
    assert not exact["accepted"]
    assert "exact duplicate" in exact["reasons"][0]
    similar = {**fresh, "source_id": "other", "sha256": "different"}
    near = quality.inspect_source(tmp_path / "clip.mp4", post("third"), [similar], config(), now=1_800_000_000)
    assert not near["accepted"]
    assert "near duplicate" in near["reasons"][0]


def test_pacing_varies_and_never_loops_or_dominates():
    sources = [
        {"source_id": str(index), "path": f"{index}.mp4", "duration": 50,
         "score": 85 - index, "opening_luma": 100, "opening_motion": 0.5}
        for index in range(3)
    ]
    shots = quality.plan_shots(sources, 58, config(), seed="fixed")
    assert shots == quality.plan_shots(sources, 58, config(), seed="fixed")
    assert sum(shot["duration"] for shot in shots) == pytest.approx(58, abs=0.05)
    assert shots[0]["duration"] <= config()["HOOK_CLIP_MAX"]
    assert max(shot["duration"] for shot in shots) <= config()["ABSOLUTE_CLIP_MAX"]
    assert len({shot["duration"] for shot in shots}) > 5
    assert all(sum(shot["duration"] for shot in shots if shot["source_id"] == source["source_id"])
               <= 58 * 0.35 + 0.01 for source in sources)
    assert all(shots[index]["source_id"] != shots[index - 1]["source_id"]
               for index in range(1, len(shots)))


def test_insufficient_distinct_sources_rejects_without_publishing():
    selected = [{"source_id": "one", "score": 90, "opening_luma": 100,
                 "source_url": "https://www.reddit.com/one", "reasons": [], "accepted": True}]
    report = quality.build_report("test", selected, selected, [], 58, config())
    assert report["decision"] == "reject"
    assert "only 1 of 3 required distinct sources" in report["reasons"]


def test_passing_quality_report_contains_required_fields(tmp_path):
    selected = [
        {"source_id": str(index), "source_url": f"https://www.reddit.com/{index}",
         "score": 85, "opening_luma": 100, "reasons": [], "accepted": True}
        for index in range(3)
    ]
    shots = [{"source_id": str(index % 3), "path": "clip.mp4", "start": index * 3,
              "duration": 3.0} for index in range(18)]
    report = quality.build_report("sample", selected, selected, shots, 54, config())
    path = quality.write_report(report, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["decision"] == "publish"
    assert payload["sources_considered"] == 3
    assert payload["final_quality_score"] >= 75
    assert payload["longest_clip_duration"] == 3


def test_history_merge_retains_recent_hashes():
    old = {"version": 1, "recent_videos": [{"video_id": "a", "sources": [{"sha256": "one"}]}]}
    new = {"version": 1, "recent_videos": [{"video_id": "b", "sources": [{"sha256": "two"}]}]}
    assert [item["video_id"] for item in merge_states(old, new)["recent_videos"]] == ["a", "b"]


def test_workflow_only_uploads_after_quality_pass():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/create-short.yml").read_text(encoding="utf-8")
    assert "steps.render.outputs.publish == 'true'" in workflow
    assert "quality_reports/*.json" in workflow


def test_higher_resolution_variant_is_preferred():
    variants = reddit_direct_variants("https://v.redd.it/abc/DASH_720.mp4?source=fallback")
    assert variants[0] == "https://v.redd.it/abc/DASH_1080.mp4?source=fallback"
    assert variants[1].endswith("DASH_720.mp4?source=fallback")
