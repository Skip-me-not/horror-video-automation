from __future__ import annotations

import json
import os
import random
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


REQUIRED_FIELDS = {
    "id", "content_type", "evidence_type", "category", "location", "source_id",
    "source_title", "source_url", "source_institution", "source_date", "source_collection",
    "source_rights", "verification_note", "title", "hook", "script", "word_count",
    "estimated_duration", "quality_score", "similarity_score", "status", "created_at",
    "used_at", "youtube_video_id",
}

EVIDENCE_TYPES = {"oral_history", "folklore_record", "archival_record", "reference_summary"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ScriptBank:
    def __init__(self, path: Path, used_path: Path | None = None) -> None:
        self.path = Path(path)
        self.used_path = Path(used_path) if used_path else self.path.with_name("used_scripts.json")
        self.items = self._load(self.path, [])
        if not isinstance(self.items, list):
            raise ValueError("script bank must be a JSON array")

    @staticmethod
    def _load(path: Path, default: object) -> object:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {path}") from exc

    def save(self) -> None:
        atomic_write_json(self.path, self.items)

    def add(self, script: dict[str, object]) -> None:
        if len(self.items) >= 500:
            raise ValueError("script bank cannot exceed 500 scripts")
        if set(script) < REQUIRED_FIELDS:
            missing = sorted(REQUIRED_FIELDS - set(script))
            raise ValueError(f"script is missing fields: {', '.join(missing)}")
        if any(item.get("id") == script["id"] for item in self.items):
            raise ValueError(f"duplicate script ID: {script['id']}")
        self.items.append(script)
        self.save()

    def ready(self) -> list[dict[str, object]]:
        return [item for item in self.items if item.get("status") == "ready"]

    def select_unused(self, rng: random.Random | None = None) -> dict[str, object]:
        used = self._load(self.used_path, [])
        used_ids = {str(item.get("id")) for item in used} if isinstance(used, list) else set()
        ready = [item for item in self.ready() if str(item.get("id")) not in used_ids]
        if not ready:
            raise RuntimeError("no unused READY scripts remain")
        recent_categories = [item.get("category") for item in used[-6:]] if isinstance(used, list) else []
        counts = Counter(recent_categories)
        lowest = min(counts.get(str(item.get("category")), 0) for item in ready)
        diverse = [item for item in ready if counts.get(str(item.get("category")), 0) == lowest]
        return (rng or random.SystemRandom()).choice(diverse)

    def mark_used(self, script_id: str, youtube_video_id: str) -> dict[str, object]:
        if not youtube_video_id.strip():
            raise ValueError("youtube_video_id is required")
        item = self.get(script_id)
        if item.get("status") != "ready":
            raise ValueError(f"script {script_id} is not READY")
        item["status"] = "used"
        item["used_at"] = utc_now()
        item["youtube_video_id"] = youtube_video_id
        used = self._load(self.used_path, [])
        if not isinstance(used, list):
            raise ValueError("used_scripts.json must be a JSON array")
        used.append({
            "id": script_id,
            "category": item.get("category"),
            "used_at": item["used_at"],
            "youtube_video_id": youtube_video_id,
        })
        # Write the append-only audit before the bank. Repeating after interruption is blocked by ID.
        atomic_write_json(self.used_path, used)
        self.save()
        return item

    def get(self, script_id: str) -> dict[str, object]:
        for item in self.items:
            if item.get("id") == script_id:
                return item
        raise KeyError(script_id)

    def validate(self) -> list[str]:
        errors: list[str] = []
        ids: set[str] = set()
        source_urls: set[str] = set()
        for index, item in enumerate(self.items, 1):
            missing = REQUIRED_FIELDS - set(item)
            if missing:
                errors.append(f"item {index}: missing {', '.join(sorted(missing))}")
            expected = f"HF{index:04d}"
            if item.get("id") != expected:
                errors.append(f"item {index}: expected ID {expected}")
            if item.get("id") in ids:
                errors.append(f"item {index}: duplicate ID {item.get('id')}")
            ids.add(str(item.get("id")))
            if item.get("status") not in {"ready", "used"}:
                errors.append(f"item {index}: invalid status")
            if item.get("content_type") != "sourced_horror_fact":
                errors.append(f"item {index}: content_type must be sourced_horror_fact")
            if item.get("evidence_type") not in EVIDENCE_TYPES:
                errors.append(f"item {index}: invalid evidence_type")
            source_url = str(item.get("source_url", ""))
            if not source_url.startswith(("https://www.loc.gov/item/", "https://loc.gov/item/", "https://en.wikipedia.org/wiki/")):
                errors.append(f"item {index}: source_url must be an approved direct source URL")
            if source_url in source_urls:
                errors.append(f"item {index}: duplicate source_url")
            source_urls.add(source_url)
            if not 60 <= int(item.get("word_count", 0)) <= 100:
                errors.append(f"item {index}: word_count must be 60-100")
            if not str(item.get("verification_note", "")).strip():
                errors.append(f"item {index}: verification_note is required")
        if len(self.items) > 500:
            errors.append("bank contains more than 500 scripts")
        return errors


def category_counts(items: Iterable[dict[str, object]]) -> Counter[str]:
    return Counter(str(item.get("category", "")) for item in items)
