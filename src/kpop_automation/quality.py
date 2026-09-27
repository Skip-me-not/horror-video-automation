from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.validator import validate_story_short


def validate(topic: dict[str, Any], script: dict[str, Any], assets: list[dict[str, Any]],
             video: Path, minimum: float, maximum: float) -> dict[str, Any]:
    errors: list[str] = []
    if not topic.get("sources") or not topic.get("claims"):
        errors.append("topic lacks cited sources or claims")
    if topic.get("review_reason"):
        errors.append(f"manual review required: {topic['review_reason']}")
    if not 120 <= int(script.get("word_count", 0)) <= 150:
        errors.append("narration must have 120–150 source-grounded words")
    source_ids = {item.get("source_id") for item in topic.get("sources", [])}
    if not set(script.get("source_ids", [])).issubset(source_ids):
        errors.append("script cites an unknown source")
    for asset in assets:
        if not asset.get("approved") or asset.get("license") in {"", "unknown", "unverified"}:
            errors.append(f"asset is not licensed: {asset.get('id', 'unknown')}")
    result = validate_story_short(video, minimum, maximum)
    errors.extend(result.errors)
    report = {"valid": not errors, "errors": errors, "probe": result.probe,
              "checks": {"sources": True, "claims": True, "asset_licenses": not any("asset" in x for x in errors)}}
    return report
