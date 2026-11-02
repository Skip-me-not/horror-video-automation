from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import bl_renderer
from scripts.bl_ranked_renderer import SEGMENT_DURATIONS, build_ranked_ass, download_reddit_source, ranked_package
from scripts.bl_engine import (
    BLEngineError,
    content_fingerprint,
    default_state,
    duplicate_reasons,
    generate_package,
    load_catalogs,
    normalized_url,
    record_success,
    source_score,
    split_captions,
    validate_story,
    verification_result,
)
from scripts.bl_source import classify, feed_entries, feed_relevance, reddit_story, story_from_entry, validated_feed_url
from scripts.merge_bl_state import merge_history

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def story() -> dict:
    return json.loads((ROOT / "data" / "queue" / "sample-casting.json").read_text(encoding="utf-8"))


def test_manifest_has_100_unique_templates_and_18_categories():
    _, manifest, _ = load_catalogs()
    templates = manifest["templates"]
    assert len(templates) == 100
    assert len({item["id"] for item in templates}) == 100
    assert len({item["category"] for item in templates}) == 18


def test_every_template_references_valid_layout_and_caption():
    config, manifest, _ = load_catalogs()
    layouts = {item["id"] for item in config["layouts"]}
    captions = set(config["caption_profiles"])
    assert len(layouts) == 18
    assert all(item["scene_layout"] in layouts for item in manifest["templates"])
    assert all(item["caption_profile"] in captions for item in manifest["templates"])


def test_story_validation_and_variable_replacement(story):
    config, manifest, _ = load_catalogs()
    assert validate_story(story, config, manifest) == []
    package = generate_package(story, default_state())
    assert "{" not in package["script"]["narration"]
    assert "Arun Lee" in package["script"]["narration"]
    assert package["metadata"]["title"]


def test_missing_optional_lines_are_removed(story):
    story.pop("date")
    package = generate_package(story, default_state())
    assert "{}" not in package["script"]["narration"]
    assert all(line.strip() for line in package["script"]["body"])


def test_missing_required_fields_fail_cleanly(story):
    story.pop("actor_2")
    with pytest.raises(BLEngineError, match="lacks fields"):
        generate_package(story, default_state())


def test_verification_scoring_and_sensitive_override(story):
    config, _, _ = load_catalogs()
    score, _ = source_score(story, config)
    assert score == 100
    assert verification_result(story, config)["decision"] == "auto_publish"
    story["context"] = "an unverified dating relationship claim"
    result = verification_result(story, config)
    assert result["decision"] == "manual_review"
    assert "dating" in result["sensitive_topics"]


def test_reddit_alone_cannot_auto_publish(story):
    config, _, _ = load_catalogs()
    story["sources"] = [{"type": "reddit", "name": "Reddit", "url": "https://reddit.com/r/test/1"}]
    assert verification_result(story, config)["decision"] == "reject"


def test_duplicate_detection_tracks_all_keys(story):
    package = generate_package(story, default_state())
    state = record_success(package, default_state(), youtube_video_id="abc123")
    reasons = duplicate_reasons(story, state)
    assert "story_id already published" in reasons
    assert "source URL already published" in reasons
    assert "normalized headline already published" in reasons
    assert "content fingerprint already published" in reasons


def test_template_rotation_avoids_last_ten(story):
    first = generate_package(story, default_state())
    state = default_state()
    state["template_history"] = [first["template"]["id"]]
    state["hook_history"] = [first["template"]["hook_pattern"]]
    state["layout_history"] = [first["layout"]["id"]]
    second = generate_package(story, state)
    assert second["template"]["id"] != first["template"]["id"]
    assert second["layout"]["id"] != first["layout"]["id"]


def test_caption_split_is_at_most_two_lines():
    captions = split_captions("This is a deliberately long sentence that needs readable mobile caption segments. Another sentence follows.", max_chars=20, max_lines=2)
    assert len(captions) >= 2
    assert all(len(item.splitlines()) <= 2 for item in captions)
    assert all(len(line) <= 40 for item in captions for line in item.splitlines())


def test_cover_definition_contains_category_and_brand_without_duplicate_headline(story):
    package = generate_package(story, default_state())
    cover = bl_renderer.build_cover_ass(package, "Lululala")
    assert "CASTING" in cover
    assert "Lululala" in cover
    assert "Arun Lee and Min Park" not in cover


def test_metadata_catalog_rotation(story):
    first = generate_package(story, default_state())
    state = default_state()
    state["title_pattern_history"] = [first["catalog_choices"]["title_pattern"]]
    second = generate_package(story, state)
    assert second["catalog_choices"]["title_pattern"] != first["catalog_choices"]["title_pattern"]
    assert "Sources:" in second["metadata"]["description"]
    assert second["metadata"]["source_urls"]


def test_content_fingerprint_is_stable(story):
    assert content_fingerprint(story) == content_fingerprint(copy.deepcopy(story))


def test_state_merge_preserves_repeated_rotation_events():
    assert merge_history(["a", "b", "a"], ["a", "b", "c"]) == ["a", "b", "a", "c"]


def test_feed_parser_and_category_classifier():
    xml = b"<rss><channel><item><title>New BL trailer released</title><link>https://example.com/trailer</link><description>Official preview.</description></item></channel></rss>"
    entries = feed_entries(xml, "https://example.com/feed")
    assert entries[0]["url"] == "https://example.com/trailer"
    assert classify(entries[0]["headline"]) == "trailer_release"


def test_youtube_feed_story_uses_related_media_and_clean_script():
    xml = b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
      <entry><title>New BL Trailer | Official Channel</title><link href="https://www.youtube.com/watch?v=abcDEF_1234"/>
      <published>2026-10-01T07:00:13+00:00</published><media:group><media:description>Two rivals are forced to work together.</media:description>
      <media:thumbnail url="https://i.ytimg.com/vi/abcDEF_1234/hqdefault.jpg"/></media:group></entry></feed>'''
    entry = feed_entries(xml, "https://www.youtube.com/feeds/videos.xml?channel_id=test")[0]
    story = story_from_entry(entry, {"name": "Official Channel", "company": "Studio", "country": "Thailand", "source_type": "official"})
    assert story["series"] == "New BL Trailer"
    assert story["assets"][0]["role"] == "source_video"
    assert story["assets"][-1]["role"] == "source_thumbnail"
    package = generate_package(story, default_state())
    assert "official first look" in package["script"]["hook"]
    assert len(package["script"]["body"]) >= 2
    assert len(package["script"]["narration"]) < 500


def test_youtube_feed_keeps_required_channel_query():
    url = "https://www.youtube.com/feeds/videos.xml?channel_id=UC8BzJM6_VbZTdiNLD4R1jxQ"
    assert validated_feed_url(url) == url
    assert validated_feed_url("http://www.youtube.com/feeds/videos.xml?channel_id=x") == ""


def test_youtube_watch_normalization_keeps_video_identity_only():
    source = "https://www.youtube.com/watch?v=abcDEF_1234&utm_source=feed&feature=youtu.be"
    assert normalized_url(source) == "https://www.youtube.com/watch?v=abcDEF_1234"


def test_feed_relevance_prefers_news_and_rejects_episode_noise():
    assert feed_relevance("Official Trailer: A New BL Series", "trailer_release") > 0
    assert feed_relevance("[BTS] Episode 4 behind the scenes", "general_entertainment") < 0
    assert feed_relevance("LIVE! KHEMJIRA WELCOME BACK", "comeback") < 0


def test_qa_checks_valid_probe(monkeypatch, tmp_path, story):
    package = generate_package(story, default_state())
    video = tmp_path / "short.mp4"
    video.write_bytes(b"0" * 120_000)
    monkeypatch.setattr(bl_renderer, "ffprobe", lambda _: {"streams": [
        {"codec_type": "video", "width": 1080, "height": 1920, "codec_name": "h264"},
        {"codec_type": "audio", "codec_name": "aac"}], "format": {"duration": "48.0"}})
    report = bl_renderer.qa_report(package, video, [], False)
    assert report["passed"] is True


def test_qa_rejects_unverified_story(monkeypatch, tmp_path, story):
    package = generate_package(story, default_state())
    package["verification"]["decision"] = "manual_review"
    video = tmp_path / "short.mp4"
    video.write_bytes(b"0" * 120_000)
    monkeypatch.setattr(bl_renderer, "ffprobe", lambda _: {"streams": [
        {"codec_type": "video", "width": 1080, "height": 1920, "codec_name": "h264"},
        {"codec_type": "audio", "codec_name": "aac"}], "format": {"duration": "48.0"}})
    assert "source verification does not allow automatic publication" in bl_renderer.qa_report(package, video, [], False)["issues"]


def test_reference_ranked_package_has_six_reveals_and_sixty_second_pacing(story):
    stories = []
    for index in range(6):
        item = copy.deepcopy(story)
        item["story_id"] = f"ranked-{index}"
        item["series"] = f"BL Series {index + 1}"
        item["sources"][0]["url"] = f"https://example.com/source-{index}"
        stories.append(item)
    package = ranked_package(stories, default_state())
    subtitles = build_ranked_ass(package)
    assert sum(SEGMENT_DURATIONS) == 60
    assert [item["rank"] for item in package["ranked_items"]] == [6, 5, 4, 3, 2, 1]
    assert package["metadata"]["title"] == "Top 6 BL Moments You Need to See"
    assert "Top 6" in subtitles and "BL Series 6" in subtitles and "BL Series 1" in subtitles
    assert "Lululala" in subtitles


def test_reddit_ranked_package_needs_no_cookie_secret():
    stories = []
    for index in range(6):
        post = {
            "id": f"reddit-{index}",
            "title": f"BL moment number {index + 1} from a public scene",
            "subreddit": "boyslove",
            "score": 1000 - index,
            "num_comments": 100,
            "created_utc": 1_750_000_000,
            "permalink": f"/r/boyslove/comments/reddit{index}/source/",
            "video_url": f"https://v.redd.it/clip{index}/DASH_720.mp4?source=fallback",
        }
        stories.append(reddit_story(post))
    package = ranked_package(stories, default_state())
    assert package["verification"]["decision"] == "auto_publish"
    assert all(item["story"]["assets"][0]["role"] == "reddit_source_video" for item in package["ranked_items"])


def test_reddit_ranked_download_uses_direct_manifest_without_cookies(monkeypatch, tmp_path):
    item = {
        "rank": 6,
        "source_url": "https://www.reddit.com/r/boyslove/comments/abc/source/",
        "story": {"assets": [{
            "role": "reddit_source_video",
            "url": "https://v.redd.it/clipabc/DASH_720.mp4?source=fallback",
            "source_url": "https://www.reddit.com/r/boyslove/comments/abc/source/",
        }]},
    }
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"video" * 3000)
        return type("Result", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("scripts.bl_ranked_renderer.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.bl_ranked_renderer.has_audio", lambda _path: True)
    result = download_reddit_source(item, tmp_path, 0)
    assert result.is_file()
    flat = " ".join(commands[0])
    assert "cookies" not in flat.casefold()
    assert commands[0][0] == "ffmpeg"
    assert "https://v.redd.it/clipabc/HLSPlaylist.m3u8" in commands[0]
