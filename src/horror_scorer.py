from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .captions import Caption


@dataclass(frozen=True)
class ScoredMoment:
    caption: Caption
    score: float
    categories: tuple[str, ...]
    matches: tuple[str, ...]


class HorrorScorer:
    def __init__(self, triggers: dict[str, list[str]], scoring: dict[str, Any]) -> None:
        self.triggers = triggers
        self.weights = scoring["weights"]
        self.proximity_bonus = float(scoring.get("proximity_bonus", 2.5))

    def score(self, caption: Caption) -> ScoredMoment:
        lowered = caption.text.casefold()
        categories: list[str] = []
        matches: list[str] = []
        total = 0.0
        for category, phrases in self.triggers.items():
            found = [phrase for phrase in phrases if phrase.casefold() in lowered]
            if found:
                categories.append(category)
                matches.extend(found)
                total += float(self.weights.get(category, 1.0)) + min(2, len(found) - 1) * 0.5
        if len(categories) >= 2:
            total += self.proximity_bonus
        if any(mark in caption.text for mark in ("!", "?", "...")):
            total += 0.4
        return ScoredMoment(caption, round(total, 3), tuple(categories), tuple(dict.fromkeys(matches)))

    def score_all(self, captions: list[Caption]) -> list[ScoredMoment]:
        return sorted((self.score(caption) for caption in captions), key=lambda item: item.score, reverse=True)
