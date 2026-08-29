from __future__ import annotations

from copy import deepcopy
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
                    broll_min: float, broll_max: float, max_static: float,
                    target_count: int = 5, max_count: int = 7) -> dict[str, Any]:
    inserts: list[dict[str, Any]] = []
    previous_end = float(hook["duration"])
    for index, event in enumerate(query_events):
        if len(inserts) >= min(target_count, max_count):
            continue
        start = max(float(hook["duration"]) + 4.0, float(event["time"]))
        if start < previous_end + 7.0 or start >= final_duration - 5.0:
            continue
        duration = min(broll_max, max(broll_min, 3.0 + (index % 3) * 0.55))
        end = min(final_duration - 5.0, start + duration)
        if end - start < broll_min:
            continue
        asset = stock_assets.get(event["query"])
        kind = ("broll_video" if asset and asset["media_type"] == "video" else
                "reference_image" if asset else "planned_broll")
        insert = {"type": kind, "start": round(start, 3), "end": round(end, 3),
                  "query": event["query"], "keyword": event["keyword"],
                  "preferred_media_type": "video" if index % 2 == 0 else "image"}
        if asset:
            insert["asset"] = asset
        inserts.append(insert)
        previous_end = end

    segments: list[dict[str, Any]] = [{"type": "hook", "start": 0.0,
                                      "end": round(float(hook["duration"]), 3), "text": hook["text"]}]
    cursor = float(hook["duration"])
    for insert in inserts:
        segments.extend(_split_podcast(cursor, float(insert["start"]), max_static))
        segments.append(insert)
        cursor = float(insert["end"])
    segments.extend(_split_podcast(cursor, final_duration, max_static))
    coverage = sum(float(item["end"]) - float(item["start"])
                   for item in segments if item["type"] in {"broll_video", "reference_image", "planned_broll"})
    plan = {"final_duration": round(final_duration, 3), "source_speed": speed,
            "horizontal_flip": horizontal_flip, "broll_ratio": round(coverage / final_duration, 4),
            "planned_broll_count": len(inserts), "segments": segments,
            "source_audio_continuous": True}
    validate_edit_plan(plan)
    return plan


def attach_stock_assets(plan: dict[str, Any], stock_assets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    finalized = deepcopy(plan)
    used = 0
    for segment in finalized["segments"]:
        if segment["type"] != "planned_broll":
            continue
        asset = stock_assets.get(segment["query"])
        if not asset:
            start, end = segment["start"], segment["end"]
            segment.clear()
            segment.update({"type": "podcast", "start": start, "end": end,
                            "crop_variant": 1.0})
            continue
        segment["type"] = "broll_video" if asset["media_type"] == "video" else "reference_image"
        segment["asset"] = asset
        used += 1
    finalized["stock_asset_count"] = used
    covered = sum(float(item["end"]) - float(item["start"])
                  for item in finalized["segments"] if item["type"] in {"broll_video", "reference_image"})
    finalized["broll_ratio"] = round(covered / float(finalized["final_duration"]), 4)
    validate_edit_plan(finalized)
    return finalized


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
