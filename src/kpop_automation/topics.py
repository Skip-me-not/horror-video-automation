from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from .models import SourceRecord, Topic

STOP = {"the", "and", "for", "with", "from", "after", "about", "into", "their", "this", "that", "says", "korean", "kpop"}


def _tokens(title: str, entity: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", title.casefold()))
    return {word for word in words - set(re.findall(r"[a-z0-9]+", entity.casefold())) - STOP if len(word) > 2}


def _same_event(left: SourceRecord, right: SourceRecord, entity: str) -> bool:
    a, b = _tokens(left.title, entity), _tokens(right.title, entity)
    return bool(a and b and len(a & b) / len(a | b) >= 0.35)


def _age_hours(record: SourceRecord) -> float | None:
    try:
        published = datetime.fromisoformat(record.published_at.replace("Z", "+00:00"))
        if published.tzinfo is None:
            return None
        return (datetime.now(timezone.utc) - published).total_seconds() / 3600
    except ValueError:
        return None


def _domain(record: SourceRecord) -> str:
    return urlsplit(record.url).netloc.lower().removeprefix("www.")


def rank_topics(records: list[SourceRecord], state: dict[str, Any], config: dict[str, Any],
                category_override: str = "") -> list[Topic]:
    research = config["research"]
    used = set(state.get("used_articles", []))
    covered = {item.get("topic_id") for item in state.get("covered_topics", [])}
    recent = Counter(item.get("entity") for item in state.get("entity_history", [])[-16:])
    eligible = []
    for record in records:
        age = _age_hours(record)
        if (record.source_id not in used and age is not None and -2 <= age <= int(research.get("max_age_days", 2)) * 24
                and (not category_override or record.category == category_override)):
            eligible.append(record)
    eligible.sort(key=lambda item: (item.reliability, item.published_at), reverse=True)
    groups: list[tuple[str, list[SourceRecord]]] = []
    for record in eligible:
        entity = record.entities[0]
        match = next((items for label, items in groups if label == entity and _same_event(items[0], record, entity)), None)
        if match is None:
            groups.append((entity, [record]))
        elif _domain(record) not in {_domain(item) for item in match}:
            match.append(record)
    ranked: list[Topic] = []
    for entity, items in groups:
        primary = items[0]
        domains = {_domain(item) for item in items}
        official = any(item.source_kind == "official" and item.reliability >= 3 for item in items)
        corroborated = len(domains) >= 2
        measured_age = _age_hours(primary)
        age = max(0, measured_age if measured_age is not None else 999)
        freshness = 30 if age <= 24 else 20 if age <= 48 else 0
        popularity = max(0, 25 - recent[entity] * 8)
        single_reliable_report = primary.reliability >= 2 and primary.source_kind in {"entertainment_news", "trade_press", "broadcaster", "government"}
        verification = 20 if official or corroborated else 10 if single_reliable_report else 0
        visual = 10  # Original, rights-safe motion graphics are always available.
        interest = 5 if primary.category in {"trending_news", "viral_moments"} else 3
        international = 10 if primary.reliability >= 2 else 0
        breakdown = {"freshness": freshness, "popularity": popularity, "sources": verification,
                     "visual_availability": visual, "international_relevance": international,
                     "story_interest": interest}
        score = min(100, sum(breakdown.values()))
        key = hashlib.sha256((entity.casefold() + "|" + " ".join(sorted(_tokens(primary.title, entity)))).encode()).hexdigest()[:20]
        if key in covered:
            continue
        reason = "" if official or corroborated or single_reliable_report else "needs one reliable original report"
        if score < 75:
            reason = reason or f"news score {score} is below the 75-point publishing threshold"
        claims = tuple(dict.fromkeys(item.title for item in items)) + tuple(dict.fromkeys(item.evidence for item in items if item.evidence != item.title))
        ranked.append(Topic(key, primary.title, primary.category, entity, tuple(items), claims, reason, score, breakdown))
    return sorted(ranked, key=lambda item: (-item.score, item.topic_id))
