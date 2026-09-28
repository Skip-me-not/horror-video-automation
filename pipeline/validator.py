from __future__ import annotations

from pathlib import Path

from src.validator import validate_story_short


def validate(path: Path) -> dict:
    result = validate_story_short(path, minimum=5, maximum=180)
    if not result.valid:
        raise ValueError("render validation failed: " + "; ".join(result.errors))
    return {"valid": True, "duration": float(result.probe["format"]["duration"]),
            "bytes": path.stat().st_size}
