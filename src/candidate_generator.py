from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .captions import Caption
from .horror_scorer import ScoredMoment


def generate_candidates(captions: list[Caption], moments: list[ScoredMoment], minimum_score: float,
                        limit: int = 20) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for moment in moments:
        if moment.score < minimum_score:
            continue
        nearby = [caption.text for caption in captions
                  if caption.start <= moment.caption.end + 12 and caption.end >= moment.caption.start - 12]
        candidates.append({
            "anchor": asdict(moment.caption),
            "score": moment.score,
            "categories": list(moment.categories),
            "matches": list(moment.matches),
            "context": " ".join(nearby),
        })
        if len(candidates) >= limit:
            break
    return candidates
