import random
from unittest.mock import Mock

import pytest

from scripts.consume_quote import consume_quote
from scripts.merge_state import merge_states
from scripts.render_short import (
    MUSIC_DUCK_RATIO,
    MUSIC_DUCK_THRESHOLD,
    MUSIC_MIX_VOLUME,
    ShortsError,
    build_ass_subtitles,
    build_metadata,
    load_quotes,
    locate_font,
    make_hook,
    make_title,
    quote_to_impact_story,
    select_quote,
    suitable_video_files,
    suitable_openverse_audio,
    search_openverse_audio,
    validate_channel_name,
    wrap_quote,
)


def test_background_music_stays_audible_beneath_narration():
    assert 0.2 <= MUSIC_MIX_VOLUME <= 0.3
    assert MUSIC_DUCK_THRESHOLD >= 0.05
    assert MUSIC_DUCK_RATIO <= 4


def sample_quotes():
    return [
        {"id": "q001", "quote": "A steady step can carry a brave plan forward.", "insight": "Choose one useful action and finish it today.", "pexels_search": "walking sunrise", "category": "consistency"},
        {"id": "q002", "quote": "Useful work becomes confidence when repeated.", "insight": "Practice the skill before asking confidence to appear.", "pexels_search": "focused worker", "category": "confidence"},
        {"id": "q003", "quote": "Choose the direction that makes tomorrow stronger.", "insight": "Make the next decision from values instead of fear.", "pexels_search": "mountain road", "category": "growth"},
    ]


def test_quote_selection_never_restarts_an_exhausted_catalog():
    state = {"version": 1, "cycle": 1, "used_ids": [], "history": []}
    rng = random.Random(7)
    selected = [select_quote(sample_quotes(), state, rng=rng)["id"] for _ in range(3)]
    assert len(set(selected)) == 3
    with pytest.raises(ShortsError, match="already marked as used"):
        select_quote(sample_quotes(), state, rng=rng)


def test_wrap_quote_respects_line_width_and_safe_line_count():
    wrapped = wrap_quote("Patient effort gives every difficult goal a fair chance to become real.", width=22, max_lines=5)
    lines = wrapped.splitlines()
    assert len(lines) <= 5
    assert all(len(line) <= 22 for line in lines)


def test_metadata_contains_attribution_quote_and_safe_title():
    entry = sample_quotes()[0]
    metadata = build_metadata(
        entry,
        creator_name="Example Creator",
        source_url="https://www.pexels.com/video/example-123/",
        channel_name="Daily Resolve",
        privacy_status="private",
        music_name="Sad Piano",
        music_creator="Example Musician",
        music_source_url="https://freesound.org/example/",
        music_license="CC0",
    )
    assert len(metadata["title"]) <= 100
    assert metadata["title"].endswith("#shorts")
    assert entry["quote"] in metadata["description"]
    assert entry["insight"] in metadata["description"]
    assert "Example Creator" in metadata["description"]
    assert "Sad Piano" in metadata["description"]
    assert metadata["music_license"] == "CC0"
    assert metadata["made_for_kids"] is False
    assert metadata["privacy_status"] == "private"


def test_long_title_is_capped_at_one_hundred_characters():
    title = make_title("steady progress " * 20)
    assert len(title) <= 100
    assert title.endswith("#shorts")


def test_every_catalog_quote_fits_the_render_safe_area():
    for entry in load_quotes():
        wrapped_quote = wrap_quote(entry["quote"], width=32, max_lines=5)
        wrapped_insight = wrap_quote(entry["insight"], width=34, max_lines=4)
        assert len(wrapped_quote.splitlines()) <= 5
        assert len(wrapped_insight.splitlines()) <= 4


def test_successful_catalog_consumption_is_permanent_and_idempotent_for_manual_text():
    entries = sample_quotes()
    remaining = consume_quote(entries, "q002")
    assert [entry["id"] for entry in remaining] == ["q001", "q003"]
    assert consume_quote(entries, "manual") == entries
    with pytest.raises(RuntimeError, match="not available"):
        consume_quote(remaining, "q002")


def test_bundled_poppins_font_is_available():
    assert locate_font().name == "Poppins-SemiBold.ttf"


def test_openverse_audio_accepts_only_long_cc0_or_public_domain_tracks():
    results = [
        {
            "id": "keep",
            "url": "https://cdn.example.com/sad-piano.mp3",
            "foreign_landing_url": "https://example.com/sounds/keep",
            "title": "Sad Piano",
            "creator": "Example Musician",
            "license": "cc0",
            "duration": 31_000,
        },
        {
            "id": "too-short",
            "url": "https://cdn.example.com/note.mp3",
            "foreign_landing_url": "https://example.com/sounds/short",
            "title": "Piano Note",
            "creator": "Example Musician",
            "license": "cc0",
            "duration": 5_000,
        },
        {
            "id": "noncommercial",
            "url": "https://cdn.example.com/restricted.mp3",
            "foreign_landing_url": "https://example.com/sounds/restricted",
            "title": "Restricted Piano",
            "creator": "Example Musician",
            "license": "by-nc",
            "duration": 60_000,
        },
    ]
    assert [item["id"] for item in suitable_openverse_audio(results)] == ["keep"]


def test_openverse_music_falls_back_when_story_queries_are_too_specific(monkeypatch):
    monkeypatch.setenv("OPENVERSE_CLIENT_ID", "client")
    monkeypatch.setenv("OPENVERSE_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {"access_token": "token"}
    empty_response = Mock()
    empty_response.raise_for_status.return_value = None
    empty_response.json.return_value = {"results": []}
    fallback_response = Mock()
    fallback_response.raise_for_status.return_value = None
    fallback_response.json.return_value = {
        "results": [
            {
                "id": "fallback",
            "url": "https://cdn.example.com/epic.mp3",
            "foreign_landing_url": "https://example.com/epic",
            "title": "Epic Motivation",
                "creator": "Example Musician",
                "license": "cc0",
                "duration": 30_000,
            }
        ]
    }
    session = Mock()
    session.post.return_value = token_response

    def fake_get(_url, *, params, **_kwargs):
        return fallback_response if params["q"] == "epic motivational music" else empty_response

    session.get.side_effect = fake_get
    selected = search_openverse_audio(
        queries=["dark focused piano"],
        minimum_seconds=15,
        rng=random.Random(0),
        session=session,
    )

    assert selected["id"] == "fallback"
    assert selected["search_used"] == "epic motivational music"


def test_quote_bank_entry_adapts_to_direct_energetic_impact_format():
    adapted = quote_to_impact_story(sample_quotes()[0])

    assert adapted["quote_text"] == sample_quotes()[0]["quote"]
    assert adapted["catalog_file"] == "data/quotes.json"
    assert adapted["hook_visual"] == sample_quotes()[0]["pexels_search"]
    assert all("piano" not in query for query in adapted["music_searches"])


def test_channel_name_is_limited_to_safe_width():
    assert validate_channel_name("  Daily   Resolve  ") == "Daily Resolve"


def test_new_subtitle_story_has_four_timed_phases_and_animation():
    entry = sample_quotes()[0]
    subtitles = build_ass_subtitles(entry, "Daily Resolve")
    assert make_hook(entry) in subtitles
    assert "A steady step can carry a brave" in subtitles
    assert r"\Nplan forward." in subtitles
    assert "DO THIS TODAY" in subtitles
    assert "SAVE THIS FOR TOMORROW" in subtitles
    assert r"\fad(" in subtitles
    assert r"\pos(540,1700)" in subtitles
    assert "Style: Channel,Poppins SemiBold,30,&H10FFFFFF" in subtitles
    assert "0:00:16.20,0:00:20.00" in subtitles


def test_pexels_candidates_keep_only_best_file_from_each_distinct_video():
    videos = [
        {
            "url": "https://www.pexels.com/video/one/",
            "user": {"name": "Creator One"},
            "video_files": [
                {"link": "https://cdn.example.com/one-low.mp4", "file_type": "video/mp4", "width": 540, "height": 960},
                {"link": "https://cdn.example.com/one-best.mp4", "file_type": "video/mp4", "width": 1080, "height": 1920},
            ],
        },
        {
            "url": "https://www.pexels.com/video/two/",
            "user": {"name": "Creator Two"},
            "video_files": [
                {"link": "https://cdn.example.com/two.mp4", "file_type": "video/mp4", "width": 1080, "height": 1920},
            ],
        },
    ]
    candidates = suitable_video_files(videos)
    assert len(candidates) == 2
    assert {item["source_url"] for item in candidates} == {
        "https://www.pexels.com/video/one/",
        "https://www.pexels.com/video/two/",
    }
    assert "https://cdn.example.com/one-best.mp4" in {
        item["download_url"] for item in candidates
    }


def test_state_merge_is_idempotent_and_preserves_both_histories():
    current = {"version": 1, "cycle": 1, "used_ids": ["q001"], "history": [{"id": "q001", "used_at": "2026-01-01T00:00:00+00:00"}]}
    rendered = {"version": 1, "cycle": 1, "used_ids": ["q001", "q002"], "history": [{"id": "q002", "used_at": "2026-01-02T00:00:00+00:00"}]}
    merged = merge_states(current, rendered)
    assert merged["used_ids"] == ["q001", "q002"]
    assert [event["id"] for event in merged["history"]] == ["q001", "q002"]
    assert merge_states(merged, rendered) == merged


def test_newer_quote_cycle_does_not_restore_old_used_ids():
    current = {"version": 1, "cycle": 1, "used_ids": ["q001", "q002"], "history": []}
    rendered = {"version": 1, "cycle": 2, "used_ids": ["q003"], "history": []}
    merged = merge_states(current, rendered)
    assert merged["cycle"] == 2
    assert merged["used_ids"] == ["q003"]
