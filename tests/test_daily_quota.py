from scripts.content_quality import load_quality_config
from datetime import datetime, timezone

from scripts.daily_quota import rank_candidates, scheduled_slot_target, summary, tier
from scripts.merge_reddit_state import merge_states


def config():
    return load_quality_config()


def candidate(idol, score, url):
    return {"idol": idol, "report": {"video_id": idol, "final_quality_score": score},
            "selected": [{"source_url": url}]}


def test_quality_tiers_preserve_absolute_floor():
    settings = config()
    assert [tier(score, settings) for score in (80, 79, 72, 71, 65, 64)] == [
        "A", "B", "B", "C", "C", None,
    ]


def test_retry_windows_never_overfill_a_daily_slot():
    assert scheduled_slot_target(datetime(2026, 10, 19, 22, 30, tzinfo=timezone.utc)) == 1
    assert scheduled_slot_target(datetime(2026, 10, 19, 23, 10, tzinfo=timezone.utc)) == 1
    assert scheduled_slot_target(datetime(2026, 10, 20, 1, 30, tzinfo=timezone.utc)) == 2
    assert scheduled_slot_target(datetime(2026, 10, 20, 4, 30, tzinfo=timezone.utc)) == 3
    assert scheduled_slot_target(datetime(2026, 10, 20, 7, 30, tzinfo=timezone.utc)) == 4


def test_rank_uses_quality_and_daily_diversity():
    settings = config()
    recent = [{"idol": "Lisa", "sources": [{"source_url": "https://example.com/a"}]}]
    candidates = [candidate("Lisa", 99, "https://example.com/a"),
                  candidate("Jisoo", 82, "https://example.com/b")]
    winner = rank_candidates(candidates, recent, settings)
    assert winner["idol"] == "Jisoo"
    assert winner["diversity_score"] == 100
    assert candidates[0]["selection_score"] < winner["selection_score"]


def test_rank_penalizes_repeated_creator():
    settings = config()
    recent = [{"idol": "Other", "sources": [{"creator": "same", "source_url": "old"}]}]
    repeated = candidate("Lisa", 81, "fresh-a")
    repeated["selected"][0]["creator"] = "same"
    different = candidate("Jisoo", 80, "fresh-b")
    different["selected"][0]["creator"] = "new"
    assert rank_candidates([repeated, different], recent, settings)["idol"] == "Jisoo"


def test_summary_counts_only_actual_upload_ids():
    settings = config()
    reports = [{"decision": "publish", "final_quality_score": 83},
               {"decision": "publish", "final_quality_score": 70},
               {"decision": "reject", "final_quality_score": 60}]
    report = summary(settings, date="2026-10-20", topics_attempted=10, analyzed=7,
                     reports=reports, published_ids=["yt-one"],
                     selected={"video_id": "candidate", "final_quality_score": 83,
                               "daily_diversity_score": 90})
    assert report["videos_rendered"] == 3
    assert (report["tier_a"], report["tier_b"], report["tier_c"]) == (1, 0, 1)
    assert report["published"] == 1
    assert not report["quota_met"]


def test_daily_uploads_merge_without_double_counting():
    old = {"version": 1, "daily_uploads": {"2026-10-20": ["yt-one"]}}
    new = {"version": 1, "daily_uploads": {"2026-10-20": ["yt-one", "yt-two"]}}
    assert merge_states(old, new)["daily_uploads"]["2026-10-20"] == ["yt-one", "yt-two"]
