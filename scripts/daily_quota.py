"""Deterministic four-slot accounting; never counts a render as an upload."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPORT = Path(__file__).resolve().parents[1] / "quality_reports" / "daily_summary.json"
MYANMAR_TIME = timezone(timedelta(hours=6, minutes=30))


def myanmar_date() -> str:
    return datetime.now(MYANMAR_TIME).date().isoformat()


def scheduled_slot_target(now: datetime | None = None) -> int:
    """Maximum uploads allowed by the current Myanmar publishing window."""
    local = now.astimezone(MYANMAR_TIME) if now else datetime.now(MYANMAR_TIME)
    if local.hour < 8:
        return 1
    if local.hour < 11:
        return 2
    if local.hour < 14:
        return 3
    return 4


def tier(score: int, config: dict[str, Any]) -> str | None:
    if score >= config["TIER_A_SCORE"]:
        return "A"
    if score >= config["TIER_B_SCORE"]:
        return "B"
    if score >= config["MIN_FINAL_SCORE"]:
        return "C"
    return None


def rank_candidates(
    candidates: list[dict[str, Any]], recent: list[dict[str, Any]], config: dict[str, Any],
) -> dict[str, Any]:
    """Choose the strongest publishable video without repeating recent sources/topics."""
    if not candidates:
        raise ValueError("Cannot rank an empty candidate list")
    used_urls = {source.get("source_url") for video in recent[-4:]
                 for source in video.get("sources", [])}
    recent_creators = {str(source.get("creator", "")).casefold()
                       for video in recent[-4:] for source in video.get("sources", [])
                       if str(source.get("creator", "")).casefold() not in {"", "unknown"}}
    recent_topics = {str(video.get("idol", "")).casefold() for video in recent[-4:]}
    for item in candidates:
        overlap = sum(source["source_url"] in used_urls for source in item["selected"])
        repeated_creators = sum(str(source.get("creator", "")).casefold() in recent_creators
                                for source in item["selected"])
        same_topic = item["idol"].casefold() in recent_topics
        item["diversity_score"] = max(0, 100 - 25 * overlap - 10 * repeated_creators
                                       - (30 if same_topic else 0))
        item["selection_score"] = (
            item["report"]["final_quality_score"]
            - overlap * config["SELECTION_PENALTY_SHARED_SOURCE"]
            - repeated_creators * config["SELECTION_PENALTY_REPEATED_CREATOR"]
            - (config["SELECTION_PENALTY_SAME_TOPIC"] if same_topic else 0)
            + (config["SELECTION_BONUS_DIFFERENT_TOPIC"] if not same_topic else 0)
        )
    return max(candidates, key=lambda item: (item["selection_score"],
                                              item["report"]["final_quality_score"]))


def summary(
    config: dict[str, Any], *, date: str, topics_attempted: int,
    analyzed: int, reports: list[dict[str, Any]],
    published_ids: list[str], selected: dict[str, Any] | None,
) -> dict[str, Any]:
    passing = [r for r in reports if r["decision"] == "publish"]
    scores = [r["final_quality_score"] for r in passing]
    result = {
        "date": date,
        "target": config["TARGET_PUBLISHED_VIDEOS_PER_DAY"],
        "candidates_discovered": topics_attempted,
        "candidates_analyzed": analyzed,
        "videos_rendered": len(reports),
        "tier_a": sum(tier(s, config) == "A" for s in scores),
        "tier_b": sum(tier(s, config) == "B" for s in scores),
        "tier_c": sum(tier(s, config) == "C" for s in scores),
        "published": len(published_ids),
        "published_video_ids": published_ids,
        "average_quality_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "average_quality_scope": "passing_candidates_this_run",
        "diversity_score": selected.get("daily_diversity_score", 0) if selected else 0,
        "diversity_scope": "selected_candidate_vs_recent_four_videos",
        "selected_candidate_id": selected["video_id"] if selected else None,
        "selected_quality_score": selected["final_quality_score"] if selected else None,
        "quota_met": len(published_ids) >= config["TARGET_PUBLISHED_VIDEOS_PER_DAY"],
    }
    return result


def write_summary(value: dict[str, Any], path: Path = REPORT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print("DAILY PUBLISH SUMMARY: " + json.dumps(value, sort_keys=True))
