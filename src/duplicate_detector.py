from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"[a-z0-9']+", text))


def ngrams(text: str, size: int = 3) -> set[tuple[str, ...]]:
    words = normalize(text).split()
    return {tuple(words[i:i + size]) for i in range(max(0, len(words) - size + 1))}


def similarity(left: str, right: str) -> float:
    a, b = normalize(left), normalize(right)
    if not a and not b:
        return 1.0
    ga, gb = ngrams(a), ngrams(b)
    jac = len(ga & gb) / len(ga | gb) if ga or gb else 0.0
    words_a, words_b = set(a.split()), set(b.split())
    word_overlap = len(words_a & words_b) / len(words_a | words_b) if words_a or words_b else 0.0
    if jac < 0.08 and word_overlap < 0.25:
        return jac
    seq = SequenceMatcher(None, a, b).ratio()
    # SequenceMatcher notices reordered phrasing while n-grams notice copied beats.
    # Weighting avoids declaring every story that shares a genre template a duplicate.
    return (seq * 0.55) + (jac * 0.45)


@dataclass(frozen=True)
class DuplicateResult:
    duplicate: bool
    reason: str = ""
    score: float = 0.0


class DuplicateDetector:
    def __init__(self, title_threshold: float = 0.82, hook_threshold: float = 0.84,
                 story_threshold: float = 0.76) -> None:
        self.title_threshold = title_threshold
        self.hook_threshold = hook_threshold
        self.story_threshold = story_threshold

    def check(self, candidate: dict[str, object], existing: Iterable[dict[str, object]]) -> DuplicateResult:
        story = normalize(str(candidate.get("script", "")))
        fingerprint = normalize(str(candidate.get("plot_fingerprint", "")))
        source_url = str(candidate.get("source_url", "")).casefold().rstrip("/")
        is_fact = candidate.get("content_type") == "sourced_horror_fact"
        combo = tuple(normalize(str(candidate.get(key, ""))) for key in ("category", "location", "twist_type"))
        for item in existing:
            if source_url and source_url == str(item.get("source_url", "")).casefold().rstrip("/"):
                return DuplicateResult(True, "source URL", 1.0)
            if story == normalize(str(item.get("script", ""))):
                return DuplicateResult(True, "exact story", 1.0)
            if fingerprint and fingerprint == normalize(str(item.get("plot_fingerprint", ""))):
                return DuplicateResult(True, "plot fingerprint", 1.0)
            other_combo = tuple(normalize(str(item.get(key, ""))) for key in ("category", "location", "twist_type"))
            if not is_fact and combo == other_combo:
                return DuplicateResult(True, "category/location/twist combination", 1.0)
            checks = () if is_fact else (
                ("title", self.title_threshold), ("hook", self.hook_threshold), ("script", self.story_threshold),
            )
            for field, threshold in checks:
                score = similarity(str(candidate.get(field, "")), str(item.get(field, "")))
                if score >= threshold:
                    return DuplicateResult(True, f"{field} similarity", score)
        return DuplicateResult(False)
