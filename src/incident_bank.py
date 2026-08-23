from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .script_bank import atomic_write_json, utc_now


REQUIRED_INCIDENT_FIELDS = {
    "id", "title", "hook", "script", "date", "location", "source_title",
    "source_url", "important_terms", "visual_queries", "status", "used_at",
    "youtube_video_id",
}


class IncidentBank:
    def __init__(self, path: Path, used_path: Path) -> None:
        self.path, self.used_path = Path(path), Path(used_path)
        self.items = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(self.items, list) or not self.items:
            raise ValueError("incident bank must be a non-empty JSON array")

    def validate(self) -> list[str]:
        errors: list[str] = []
        ids: set[str] = set()
        for index, item in enumerate(self.items, 1):
            missing = REQUIRED_INCIDENT_FIELDS - set(item)
            if missing:
                errors.append(f"incident {index}: missing {', '.join(sorted(missing))}")
            incident_id = str(item.get("id", ""))
            if incident_id in ids:
                errors.append(f"incident {index}: duplicate ID {incident_id}")
            ids.add(incident_id)
            if not incident_id.startswith("EV"):
                errors.append(f"incident {index}: ID must start with EV")
            if item.get("status") not in {"ready", "used"}:
                errors.append(f"incident {index}: invalid status")
            if not str(item.get("source_url", "")).startswith("https://"):
                errors.append(f"incident {index}: direct HTTPS source is required")
            if not 45 <= len(str(item.get("script", "")).split()) <= 110:
                errors.append(f"incident {index}: explanation must contain 45-110 words")
            if not isinstance(item.get("important_terms"), list) or not item.get("important_terms"):
                errors.append(f"incident {index}: important_terms must be non-empty")
            if not isinstance(item.get("visual_queries"), list) or len(item.get("visual_queries", [])) < 4:
                errors.append(f"incident {index}: at least four visual queries are required")
        return errors

    def get(self, incident_id: str) -> dict[str, Any]:
        for item in self.items:
            if item.get("id") == incident_id:
                return item
        raise KeyError(incident_id)

    def select_unused(self, rng: random.Random | None = None) -> dict[str, Any]:
        used = json.loads(self.used_path.read_text(encoding="utf-8")) if self.used_path.exists() else []
        used_ids = {str(item.get("id")) for item in used}
        ready = [item for item in self.items if item.get("status") == "ready" and item["id"] not in used_ids]
        if not ready:
            raise RuntimeError("no unused strange incidents remain")
        return (rng or random.SystemRandom()).choice(ready)

    def mark_used(self, incident_id: str, youtube_video_id: str) -> dict[str, Any]:
        item = self.get(incident_id)
        if item.get("status") != "ready":
            raise ValueError(f"incident {incident_id} is not READY")
        used_at = utc_now()
        item.update(status="used", used_at=used_at, youtube_video_id=youtube_video_id)
        used = json.loads(self.used_path.read_text(encoding="utf-8")) if self.used_path.exists() else []
        used.append({"id": incident_id, "category": "Documented Strange Incident",
                     "used_at": used_at, "youtube_video_id": youtube_video_id})
        atomic_write_json(self.used_path, used)
        atomic_write_json(self.path, self.items)
        return item
