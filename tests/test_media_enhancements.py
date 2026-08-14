from __future__ import annotations

import wave

from scripts.fetch_background import (
    add_credit, horror_search_query, provider_order, select_pixabay_video,
    select_video_file, visual_relevance,
)
from scripts.common import desired_background_scenes, effective_video_duration
from scripts.generate_sfx import generate_sfx
from scripts.generate_music import generate_music


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


def test_all_background_providers_are_rotated():
    order = provider_order("job-1", 0, "pexels-key", "pixabay-key")
    assert set(order) == {"pexels", "pixabay", "wikimedia", "archive"}
    assert set(order[:2]) == {"pexels", "pixabay"}


def test_background_search_is_explicitly_creepy_and_empty():
    query = horror_search_query("old hospital corridor")
    assert {"eerie", "creepy", "horror", "night", "empty"} <= set(query.split())
    assert visual_relevance(query) >= 5


def test_pixabay_selection_accepts_landscape_for_smart_crop():
    media = {"width": 1920, "height": 1080, "url": "https://cdn.pixabay.com/video/a.mp4", "size": 1000}
    video, selected = select_pixabay_video({"hits": [{"id": 9, "videos": {"medium": media}}]}, "seed")
    assert video["id"] == 9 and selected["url"].endswith("a.mp4")


def test_duration_and_scene_count_follow_narration(config):
    short = effective_video_duration(25, config, "short")
    long = effective_video_duration(95, config, "long")
    assert 25 < short < long < 180
    assert desired_background_scenes(long, config) > desired_background_scenes(short, config)


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
    assert report["continuous_layers"] == ["sub_bass_drone", "cold_wind", "distant_tone"]


def test_generated_music_is_non_melodic_creeping_dread(tmp_path):
    output = tmp_path / "music.wav"
    report = generate_music("job-1", 4.0, output, sample_rate=8000)
    with wave.open(str(output), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getnframes() == 32000
    assert report["style"] == "creeping_dissonant_dread"
    assert "detuned_sub_drone" in report["layers"]
    assert "metal_scrapes" in report["layers"]
    assert "final_sting" in report["layers"]
    assert "melody_events" not in report
