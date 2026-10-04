from __future__ import annotations

import json
import os
import shutil
import subprocess
import requests

import pytest
from PIL import Image

from src.kpop_automation.face_crop import prepare_vertical
from src.kpop_automation.media_downloader import download_approved
from src.kpop_automation.media_timeline import build_timeline
from src.kpop_automation.models import SourceRecord, Topic
from src.kpop_automation.reddit_media import candidate_from_post, discover, load_approvals, risk_score
from src.kpop_automation.video import render


def _post(title: str = "IVE at a public event") -> dict:
    return {"id": "abc", "title": title, "author": "photographer", "subreddit": "kpop",
            "permalink": "/r/kpop/comments/abc/photo/", "url": "https://i.redd.it/photo.jpg",
            "created_utc": 1_800_000_000, "is_video": False}


def test_reddit_post_is_not_permission():
    candidate = candidate_from_post(_post())
    assert candidate and not candidate["approved_for_use"]
    assert candidate["risk_score"] > 35
    assert candidate["original_source_url"] == ""
    assert candidate["reddit_username"] == "photographer"


def test_exact_permission_record_is_required(tmp_path):
    provisional = candidate_from_post(_post())
    approval = {"asset_id": provisional["asset_id"], "license": "CC-BY-4.0",
                "original_source_url": "https://photographer.example/ive-event",
                "permission_evidence_url": "https://photographer.example/license",
                "approved_by": "owner", "approved_at": "2026-09-27"}
    file = tmp_path / "approvals.json"
    file.write_text(json.dumps({"assets": [approval]}), encoding="utf-8")
    loaded = load_approvals(file)
    candidate = candidate_from_post(_post(), loaded[provisional["asset_id"]])
    assert candidate and candidate["approved_for_use"]
    assert candidate["risk_score"] <= 35
    assert not candidate_from_post(_post("IVE full drama episode"), approval)["approved_for_use"]


def test_unapproved_media_cannot_download(tmp_path):
    with pytest.raises(ValueError, match="rights approval"):
        download_approved(candidate_from_post(_post()), tmp_path)


def test_face_crop_produces_vertical_with_blurred_fill(tmp_path):
    source = tmp_path / "source.jpg"
    Image.new("RGB", (800, 600), (90, 50, 110)).save(source)
    result = prepare_vertical(source, tmp_path / "vertical.png", credit="photographer")
    with Image.open(result["path"]) as output:
        assert output.size == (1080, 1920)


def test_fixture_timeline_never_queries_reddit(tmp_path):
    source = SourceRecord("s", "IVE event", "https://news.example/ive", "News", "2026-09-27", "2026-09-27",
                          "A confirmed event.", ("IVE",), "trending_news", 2, "broadcaster")
    topic = Topic("t", "IVE event", "trending_news", "IVE", (source,), (source.title,))
    cards = [{"id": "card-1", "path": "card.png", "license": "original-generated", "approved": True}]
    timeline, errors = build_timeline(tmp_path, topic, {}, cards, "story", discover_live=False)
    assert timeline[0]["id"] == "card-1"
    assert "fixture" in errors[0]
    assert json.loads((tmp_path / "data" / "media_sources.json").read_text()) == []
    assert (tmp_path / "output" / "manifests" / "story.json").is_file()


def test_oauth_discovery_deduplicates_and_caches(tmp_path, monkeypatch):
    source = SourceRecord("s", "IVE event", "https://news.example/ive", "News", "2026-09-27", "2026-09-27",
                          "A confirmed event.", ("IVE",), "trending_news", 2, "broadcaster")
    topic = Topic("topic-ive", "IVE event", "trending_news", "IVE", (source,), (source.title,))
    monkeypatch.setenv("REDDIT_CLIENT_ID", "client")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "test:news:1.0 (by /u/tester)")
    monkeypatch.setattr("src.kpop_automation.reddit_media.time.sleep", lambda _: None)
    calls = {"search": 0}

    class Reply:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    session = requests.Session()
    monkeypatch.setattr(session, "post", lambda *args, **kwargs: Reply({"access_token": "test-token"}))

    def search(*args, **kwargs):
        calls["search"] += 1
        return Reply({"data": {"children": [{"data": _post()}]}})

    monkeypatch.setattr(session, "get", search)
    config = {"reddit": {"subreddits": ["kpop"], "request_spacing_seconds": 0}}
    first, errors = discover(topic, tmp_path, config, session)
    assert len(first) == 1 and not errors and calls["search"] == 2
    second, errors = discover(topic, tmp_path, config, session)
    assert len(second) == 1 and not errors and calls["search"] == 2


def test_mixed_image_and_short_clip_render(tmp_path):
    ffmpeg = os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("full FFmpeg not installed")
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    Image.effect_noise((540, 960), 45).convert("RGB").save(first)
    Image.effect_noise((540, 960), 80).convert("RGB").save(second)
    clip, voice = tmp_path / "approved.mp4", tmp_path / "voice.mp3"
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=360x640:rate=30", "-t", "2", "-an",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=9", "-c:a", "libmp3lame", str(voice)], check=True)
    cards = [{"path": str(first), "type": "image"}, {"path": str(clip), "type": "video"},
             {"path": str(second), "type": "image"}]
    report = render(cards, voice, [{"text": "TEST", "offset": 0, "duration": 2}],
                    {"hook": "TEST", "tags": [], "narration": "Test"}, tmp_path, 9,
                    {"width": 1080, "height": 1920, "fps": 30})
    assert report["scene_count"] == 3
    assert (tmp_path / "short.mp4").stat().st_size > 500_000
