import json
import random
from pathlib import Path

import yaml

from scripts.merge_state import merge_states
from scripts.render_short import (
    STORIES_PATH,
    build_impact_subtitles,
    build_story_metadata,
    build_story_subtitles,
    impact_beats,
    make_manual_story,
)
from scripts.story_engine import (
    MAX_SECONDS,
    MIN_SECONDS,
    estimate_beat_durations,
    hook_score,
    jaccard_similarity,
    load_stories,
    select_hook,
    select_story,
    select_title,
    similarity_terms,
    story_beats,
    story_history_event,
    story_script,
    word_count,
)


ROOT = Path(__file__).resolve().parents[1]


def stories():
    return load_stories(STORIES_PATH)


def test_catalog_is_curated_across_every_pillar_and_perspective():
    catalog = stories()
    assert len(catalog) >= 36
    assert {story["pillar"] for story in catalog} == {
        "transformation",
        "failure_comeback",
        "relatable_pain",
        "future_self",
        "disappear_rebuild",
        "hard_truth_story",
    }
    assert {story["perspective"] for story in catalog} == {
        "he", "she", "you", "first_person", "unnamed", "future_self"
    }


def test_every_story_has_mobile_beats_and_a_25_to_40_second_estimate():
    for story in stories():
        hook = select_hook(story)
        beats = story_beats(story, hook)
        durations = estimate_beat_durations(beats)
        assert 7 <= len(beats) <= 10
        assert MIN_SECONDS <= sum(durations) <= MAX_SECONDS + 0.1
        assert 55 <= word_count(story_script(story, hook)) <= 115
        assert all(word_count(beat["text"]) <= 22 for beat in beats)
        assert all(beat["visual_search"] for beat in beats)


def test_hook_engine_rejects_generic_hype_and_prefers_specific_stakes():
    assert hook_score("This will change your life.") < 0
    assert hook_score("His card declined for a meal that cost $8.40.") > hook_score(
        "He was having a difficult time."
    )
    selected = select_hook(stories()[0])
    assert selected in stories()[0]["hook_candidates"]


def test_catalog_selected_hooks_titles_and_scripts_are_not_duplicates():
    catalog = stories()
    hooks = [select_hook(story).casefold() for story in catalog]
    titles = [select_title(story).casefold() for story in catalog]
    scripts = [story_script(story).casefold() for story in catalog]
    assert len(hooks) == len(set(hooks))
    assert len(titles) == len(set(titles))
    assert len(scripts) == len(set(scripts))


def test_three_different_pillars_have_low_story_similarity():
    catalog = stories()
    examples = [
        next(story for story in catalog if story["pillar"] == pillar)
        for pillar in ("transformation", "future_self", "hard_truth_story")
    ]
    term_sets = [similarity_terms(story_script(story)) for story in examples]
    assert jaccard_similarity(term_sets[0], term_sets[1]) < 0.35
    assert jaccard_similarity(term_sets[0], term_sets[2]) < 0.35
    assert jaccard_similarity(term_sets[1], term_sets[2]) < 0.35


def test_selection_rotates_recent_pillar_topic_and_perspective():
    catalog = stories()
    first = catalog[0]
    state = {
        "version": 1,
        "cycle": 1,
        "used_ids": [first["id"]],
        "history": [story_history_event(first, select_hook(first), select_title(first))],
    }
    selected = select_story(catalog, state, rng=random.Random(9))
    assert selected["id"] != first["id"]
    assert selected["topic"] != first["topic"]


def test_rich_history_survives_state_conflict_merge():
    selected = stories()[0]
    event = story_history_event(selected, select_hook(selected), select_title(selected))
    current = {"version": 1, "cycle": 1, "used_ids": [], "history": []}
    rendered = {"version": 1, "cycle": 1, "used_ids": [selected["id"]], "history": [event]}
    merged = merge_states(current, rendered)
    assert merged["history"][0]["pillar"] == selected["pillar"]
    assert merged["history"][0]["hook"] == select_hook(selected)
    assert merged["history"][0]["similarity_terms"]


def test_story_captions_are_sequential_and_keep_channel_in_safe_area():
    selected = stories()[0]
    beats = story_beats(selected)
    durations = estimate_beat_durations(beats)
    subtitles = build_story_subtitles(beats, durations, "ORDERLESS")
    assert subtitles.count("Dialogue: 2,") == len(beats)
    assert "Style: Hook" in subtitles
    assert "Style: Turn" in subtitles
    assert r"\pos(540,500)" in subtitles
    assert r"\pos(540,1700)" in subtitles
    assert "ORDERLESS" in subtitles


def test_analytics_metadata_is_complete_and_description_is_not_stuffed():
    selected = stories()[0]
    hook = select_hook(selected)
    beats = story_beats(selected, hook)
    durations = estimate_beat_durations(beats)
    assets = [
        {
            "creator_name": f"Creator {index}",
            "source_url": f"https://www.pexels.com/video/{index}/",
            "search_used": beat["visual_search"],
        }
        for index, beat in enumerate(beats)
    ]
    music = {
        "title": "Quiet Piano",
        "creator": "Musician",
        "source_url": "https://example.com/audio",
        "license": "CC0",
        "search_used": "reflective piano",
    }
    metadata = build_story_metadata(
        selected,
        hook=hook,
        title=select_title(selected),
        beats=beats,
        duration=sum(durations),
        assets=assets,
        channel_name="ORDERLESS",
        privacy_status="private",
        music_asset=music,
    )
    for field in ("story_id", "content_pillar", "hook_type", "hook_text", "duration_seconds", "title", "script", "created_at"):
        assert metadata[field]
    assert metadata["catalog_file"] == "data/stories.json"
    assert len(metadata["title"]) <= 100
    assert metadata["description"].count("#") == 3
    assert len(metadata["pexels_assets"]) == len(beats)


def test_manual_quote_override_remains_backward_compatible():
    manual = make_manual_story("At 24, the blank page was still waiting.", "writer desk night")
    beats = story_beats(manual, manual["hook_candidates"][0])
    assert manual["id"] == "manual"
    assert beats[0]["text"] == "At 24, the blank page was still waiting."
    assert all(beat["visual_search"] == "writer desk night" for beat in beats)


def test_reddit_workflow_is_manual_and_deterministic():
    workflow = (ROOT / ".github" / "workflows" / "create-short.yml").read_text(
        encoding="utf-8"
    )
    assert "Optional idol; blank rotates data/idols.json" in workflow
    assert "AI_SCRIPT_MODE" not in workflow
    assert "GITHUB_TOKEN" not in workflow
    assert "models.github.ai" not in workflow
    assert "OPENVERSE_CLIENT_ID" not in workflow
    assert "python -m scripts.render_idol_short" in workflow
    assert "REDDIT_CLIENT_ID" not in workflow
    assert "REDDIT_CLIENT_SECRET" not in workflow


def test_workflow_yaml_preserves_public_schedule_and_success_only_rotation():
    workflow_path = ROOT / ".github" / "workflows" / "create-short.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    text = workflow_path.read_text(encoding="utf-8")
    assert text.count("- cron:") == 4
    assert "python -m scripts.upload_youtube" in text
    assert "steps.youtube.outcome == 'success'" in text
    assert "scripts.merge_reddit_state" in text
    assert "git add data/reddit_state.json" in text
    assert "INPUT_PRIVACY_STATUS: public" in text
    assert "models" not in payload["permissions"]


def test_story_json_round_trips_as_utf8():
    raw = STORIES_PATH.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert payload
    assert all(str(item["id"]).startswith("s") for item in payload)


def test_catalog_is_drawn_from_500_quality_checked_stories():
    catalog = stories()
    assert 1 <= len(catalog) <= 500
    assert len({story["id"] for story in catalog}) == len(catalog)
    assert all(1 <= int(story["id"][1:]) <= 500 for story in catalog)
    assert set(story["pillar"] for story in catalog) == {
        "transformation", "failure_comeback", "relatable_pain", "future_self",
        "disappear_rebuild", "hard_truth_story",
    }


def test_workflow_installs_and_downloads_local_tts_voice():
    workflow = (ROOT / ".github" / "workflows" / "create-short.yml").read_text(
        encoding="utf-8"
    )
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "piper-tts" in requirements
    assert "en_US-joe-medium" in workflow
    assert "actions/cache@v4" in workflow


def test_impact_quotes_are_short_original_and_caption_safe():
    catalog = stories()
    scripts = []
    for selected in catalog:
        beats = impact_beats(selected, select_hook(selected))
        text = " ".join(beat["text"] for beat in beats)
        scripts.append(text.casefold())
        assert 2 <= len(beats) <= 4
        assert 12 <= word_count(text) <= 40
        assert all(word_count(beat["text"]) <= 14 for beat in beats)
        assert word_count(beats[-1]["text"]) >= 3
    assert len(scripts) == len(set(scripts))


def test_impact_captions_match_reference_style_and_keep_branding():
    selected = stories()[0]
    beats = impact_beats(selected, select_hook(selected))
    durations = [3.0] * len(beats)
    subtitles = build_impact_subtitles(beats, durations, "ORDERLESS")
    assert subtitles.count("Dialogue: 2,") == len(beats)
    assert "Style: Impact" in subtitles
    assert r"\pos(540,780)" in subtitles
    assert "ORDERLESS" in subtitles
