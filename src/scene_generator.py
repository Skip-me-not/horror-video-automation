from __future__ import annotations

import math
import re


VISUAL_STYLE = (
    "historically grounded symbolic reconstruction, archive document texture, dark realistic horror "
    "cinematography, practical night lighting, deep shadows, vertical 9:16, no gore, no fabricated evidence"
)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


def _keywords(text: str) -> list[str]:
    stop = {"the", "and", "that", "with", "from", "into", "when", "then", "this", "while", "only", "every"}
    words = re.findall(r"[a-zA-Z]{4,}", text.casefold())
    return list(dict.fromkeys(word for word in words if word not in stop))[:7]


class SceneGenerator:
    def generate(self, script: dict[str, object]) -> list[dict[str, object]]:
        parts = _sentences(str(script["script"]))
        scene_count = min(8, max(4, math.ceil(len(parts) / 1.5)))
        buckets: list[list[str]] = [[] for _ in range(scene_count)]
        for index, sentence in enumerate(parts):
            buckets[min(scene_count - 1, index * scene_count // max(1, len(parts)))].append(sentence)
        duration = float(script.get("estimated_duration", 30))
        populated = [bucket for bucket in buckets if bucket]
        per_scene = duration / len(populated)
        scenes = []
        for index, bucket in enumerate(populated, 1):
            narration = " ".join(bucket)
            keys = _keywords(narration)
            prompt = (
                f"{script.get('source_date')} period, {script.get('location')}, {script.get('category')}, "
                f"{' '.join(keys[:4])}, {VISUAL_STYLE}"
            )
            scenes.append({
                "scene_id": index,
                "narration": narration,
                "visual_prompt": prompt,
                "keywords": keys,
                "duration": round(per_scene, 3),
            })
        return scenes
