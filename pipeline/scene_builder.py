from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def build(cards: list[dict[str, Any]], media: list[dict[str, Any]], duration: float,
          output: Path) -> list[dict[str, Any]]:
    if not cards or duration <= 5:
        raise ValueError("scene builder needs visuals and narration longer than five seconds")
    count = max(4, math.ceil(duration / 2.45))
    scenes = [dict(cards[index % len(cards)], type="image") for index in range(count)]
    for index, asset in enumerate(media[: max(0, count // 3)]):
        scenes[1 + index * 3] = dict(asset)
    weights = [1 + 0.14 * math.sin(index * 2.17) for index in range(count)]
    total = sum(weights)
    elapsed = 0.0
    timeline = []
    for index, (asset, weight) in enumerate(zip(scenes, weights)):
        length = duration * weight / total if index < count - 1 else duration - elapsed
        asset["duration"] = length
        asset["effect"] = ("punch_zoom", "pan_left", "slow_push", "pan_right")[index % 4]
        timeline.append({"start": round(elapsed, 3), "end": round(elapsed + length, 3),
                         "asset": asset["path"], "asset_id": asset["id"], "effect": asset["effect"],
                         "license": asset["license"], "source_url": asset.get("source_url", "")})
        elapsed += length
    output.mkdir(parents=True, exist_ok=True)
    (output / "timeline.json").write_text(json.dumps({"duration": duration, "scenes": timeline}, indent=2),
                                          encoding="utf-8")
    return scenes
