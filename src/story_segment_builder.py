from __future__ import annotations

from typing import Any

from .captions import Caption
from .silence_detector import nearest_boundary


def build_story_segment(captions: list[Caption], candidates: list[dict[str, Any]],
                        silences: list[dict[str, float]], source_duration: float,
                        speed: float, minimum_final: float, target_final: float,
                        maximum_final: float, ending_terms: list[str]) -> dict[str, Any]:
    if not candidates:
        raise RuntimeError("moment confidence too low; no deterministic horror anchor found")
    source_min = minimum_final * speed
    source_target = target_final * speed
    source_max = min(maximum_final * speed, 165.0)
    best: dict[str, Any] | None = None
    for candidate in candidates:
        anchor_start = float(candidate["anchor"]["start"])
        anchor_end = float(candidate["anchor"]["end"])
        start = max(0.0, anchor_start - min(70.0, source_target * 0.48))
        end = min(source_duration, max(anchor_end + 45.0, start + source_target))
        if end - start > source_max:
            start = max(0.0, end - source_max)
        boundary = nearest_boundary(start, silences, "backward")
        if boundary is not None:
            start = boundary
        boundary = nearest_boundary(end, silences, "forward")
        if boundary is not None and boundary - start <= source_max:
            end = boundary
        selected = [item for item in captions if item.end > start and item.start < end]
        transcript = " ".join(item.text for item in selected)
        ending_bonus = 2.0 if any(term in transcript.casefold()[-500:] for term in ending_terms) else 0.0
        duration = end - start
        completeness = ending_bonus + (1.0 if duration >= source_min else -4.0)
        rank = float(candidate["score"]) + completeness
        proposal = {
            "start": round(start, 3), "end": round(end, 3),
            "source_duration": round(duration, 3), "final_duration": round(duration / speed, 3),
            "anchor": candidate, "transcript": transcript, "score": round(rank, 3),
            "has_payoff_signal": bool(ending_bonus),
        }
        if best is None or proposal["score"] > best["score"]:
            best = proposal
    if best is None or best["final_duration"] < minimum_final:
        raise RuntimeError("no coherent story segment met the minimum duration")
    return best
