from __future__ import annotations

import wave

from scripts.fetch_background import add_credit, select_video_file
from scripts.generate_sfx import generate_sfx


def test_selects_portrait_pexels_mp4():
    payload = {
        "videos": [{
            "id": 42,
            "url": "https://www.pexels.com/video/42/",
            "user": {"name": "Creator"},
            "video_files": [
                {"file_type": "video/mp4", "width": 1920, "height": 1080,
                 "link": "https://videos.pexels.com/video-files/landscape.mp4"},
                {"file_type": "video/mp4", "width": 1080, "height": 1920,
                 "link": "https://videos.pexels.com/video-files/portrait.mp4"},
            ],
        }],
    }
    video, media = select_video_file(payload, "job-1")
    assert video["id"] == 42
    assert media["height"] > media["width"]


def test_pexels_credit_is_added_once():
    video = {"url": "https://www.pexels.com/video/42/", "user": {"name": "Creator"}}
    description = add_credit("Original story.", video)
    assert "Creator" in description and "Pexels" in description
    assert add_credit(description, video) == description


def test_default_text_watermark_is_centered(config):
    assert config["watermark_text"] == "SKIP IF YOU'RE SCARED"


def test_generated_sfx_is_nonempty_pcm(tmp_path):
    output = tmp_path / "sfx.wav"
    report = generate_sfx("job-1", 3.0, output, sample_rate=8000)
    assert output.stat().st_size > 1000
    with wave.open(str(output), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 8000
        assert handle.getnframes() == 24000
    assert report["events"]
