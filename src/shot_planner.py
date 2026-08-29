from __future__ import annotations

from typing import Any


def _split_podcast(start: float, end: float, maximum: float) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    cursor = start
    crop_index = 0
    while end - cursor > 0.01:
        segment_end = min(end, cursor + maximum)
        segments.append({"type": "podcast", "start": round(cursor, 3), "end": round(segment_end, 3),
                         "crop_variant": (1.0, 1.05, 1.10)[crop_index % 3]})
        cursor = segment_end
        crop_index += 1
    return segments


def build_edit_plan(final_duration: float, speed: float, horizontal_flip: bool,
                    hook: dict[str, Any], query_events: list[dict[str, Any]],
                    stock_assets: dict[str, dict[str, Any]], target_ratio: float,
                    broll_min: float, broll_max: float, max_static: float) -> dict[str, Any]:
    desired = min(final_duration * min(0.35, max(0.15, target_ratio)), final_duration - 20)
    inserts: list[dict[str, Any]] = []
    coverage = 0.0
    previous_end = float(hook["duration"])
    for index, event in enumerate(query_events):
        asset = stock_assets.get(event["query"])
        if not asset or coverage >= desired:
            continue
        start = max(float(hook["duration"]) + 4.0, float(event["time"]))
        if start < previous_end + 6.0:
            continue
        duration = min(broll_max, max(broll_min, 3.2 + (index % 3) * 0.6), desired - coverage)
        end = min(final_duration - 5.0, start + duration)
        if end - start < broll_min:
            continue
        inserts.append({"type": "broll_video" if asset["media_type"] == "video" else "reference_image",
                        "start": round(start, 3), "end": round(end, 3), "query": event["query"],
                        "keyword": event["keyword"], "asset": asset})
        coverage += end - start
        previous_end = end

    segments: list[dict[str, Any]] = [{"type": "hook", "start": 0.0,
                                      "end": round(float(hook["duration"]), 3), "text": hook["text"]}]
    cursor = float(hook["duration"])
    for insert in inserts:
        segments.extend(_split_podcast(cursor, float(insert["start"]), max_static))
        segments.append(insert)
        cursor = float(insert["end"])
    segments.extend(_split_podcast(cursor, final_duration, max_static))
    plan = {"final_duration": round(final_duration, 3), "source_speed": speed,
            "horizontal_flip": horizontal_flip, "broll_ratio": round(coverage / final_duration, 4),
            "segments": segments, "source_audio_continuous": True}
    validate_edit_plan(plan)
    return plan


def validate_edit_plan(plan: dict[str, Any]) -> None:
    segments = plan.get("segments") or []
    if not segments:
        raise ValueError("edit plan has no visual segments")
    cursor = 0.0
    for segment in segments:
        start, end = float(segment["start"]), float(segment["end"])
        if abs(start - cursor) > 0.02:
            raise ValueError(f"timeline gap or overlap at {cursor:.3f}/{start:.3f}")
        if end <= start:
            raise ValueError("timeline segment has non-positive duration")
        cursor = end
    if abs(cursor - float(plan["final_duration"])) > 0.02:
        raise ValueError("edit plan does not cover final duration")
    if cursor > 180.0:
        raise ValueError("edit plan exceeds hard 180-second maximum")
    if not plan.get("source_audio_continuous"):
        raise ValueError("source audio continuity is required")
