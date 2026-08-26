from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HistoryStore:
    def __init__(self, path: Path, limit: int = 100) -> None:
        self.path = path
        self.limit = limit

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("history.json must contain a JSON array")
        return payload

    def recent_signatures(self, count: int = 30) -> set[tuple[str, str, str]]:
        return {
            (str(item.get("game_type")), str(item.get("setting")), str(item.get("hook")))
            for item in self.load()[-count:]
        }

    def contains_hash(self, video_hash: str) -> bool:
        return any(item.get("video_hash") == video_hash for item in self.load())

    def append(self, record: dict[str, Any]) -> None:
        records = self.load()
        records.append({"timestamp": datetime.now(timezone.utc).isoformat(), **record})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(records[-self.limit :], indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
