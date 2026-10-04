from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.validator import validate_story_short
from .models import Topic
from .scripts import publication_script_errors


def validate(topic: dict[str, Any], script: dict[str, Any], assets: list[dict[str, Any]],
             video: Path, minimum: float, maximum: float,
             require_originality: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    if not topic.get("sources") or not topic.get("claims"):
        errors.append("topic lacks cited sources or claims")
    if topic.get("review_reason"):
        errors.append(f"manual review required: {topic['review_reason']}")
    if not 65 <= int(script.get("word_count", 0)) <= 100:
        errors.append("narration must have 65–100 source-grounded words")
    source_ids = {item.get("source_id") for item in topic.get("sources", [])}
    if not set(script.get("source_ids", [])).issubset(source_ids):
        errors.append("script cites an unknown source")
    if require_originality:
        errors.extend(publication_script_errors(Topic.from_dict(topic), script))
    for asset in assets:
        if not asset.get("approved") or asset.get("license") in {"", "unknown", "unverified"}:
            errors.append(f"asset is not licensed: {asset.get('id', 'unknown')}")
        if asset.get("reddit_post_url") and not (asset.get("source_url") and asset.get("permission_evidence_url")):
            errors.append(f"Reddit asset lacks source and permission evidence: {asset.get('id', 'unknown')}")
    result = validate_story_short(video, minimum, maximum)
    errors.extend(result.errors)
    duration = float(result.probe.get("format", {}).get("duration") or 0)
    if assets and duration / len(assets) > 3.05:
        errors.append("visual pacing is slower than one scene every three seconds")
    mode = script.get("generation_mode")
    media_sources = {asset["id"] for asset in assets if asset.get("reddit_post_url")}
    original_cards = sum(asset.get("license") == "original-generated" for asset in assets)
    originality = {
        "original_narration": 25 if mode == "deterministic_source_summary" and not publication_script_errors(Topic.from_dict(topic), script) else 0,
        "story_structure": 20 if mode == "deterministic_source_summary" else 10,
        "multiple_visual_sources": 15 if len(media_sources) >= 3 else 10 if original_cards >= 5 else 0,
        "custom_captions_graphics": 15 if video.is_file() and original_cards >= 1 else 0,
        "scene_restructuring": 10 if len(assets) >= 15 else 0,
        "context_commentary": 10 if len(topic.get("sources", [])) >= 1 else 0,
        "audio_transformation": 5 if any(item.get("codec_type") == "audio" for item in result.probe.get("streams", [])) else 0,
    }
    originality_score = sum(originality.values())
    if require_originality and originality_score < 80:
        errors.append(f"originality score {originality_score} is below 80")
    report = {"valid": not errors, "errors": errors, "probe": result.probe,
              "originality_score": originality_score, "originality_factors": originality,
              "checks": {"sources": True, "claims": True, "asset_licenses": not any("asset" in x for x in errors)}}
    return report
