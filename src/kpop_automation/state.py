from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def queue_manifest(state: dict[str, Any], manifest: dict[str, Any]) -> None:
    content_id, slot_id = manifest["content_id"], manifest["slot_id"]
    if slot_id in state.setdefault("slots", {}):
        raise ValueError(f"slot already completed: {slot_id}")
    state["pending"][content_id] = {
        "status": manifest["status"], "slot_id": slot_id, "created_at": manifest["created_at"],
        "category": manifest["topic"]["category"], "entity": manifest["topic"]["entity"],
    }
    state["slots"][slot_id] = content_id
    state["used_articles"] = list(dict.fromkeys(state["used_articles"] + manifest["script"]["source_ids"]))[-1000:]
    state["covered_topics"].append({"topic_id": manifest["topic"]["topic_id"], "at": manifest["created_at"]})
    state["entity_history"].append({"entity": manifest["topic"]["entity"], "at": manifest["created_at"]})
    state["hook_history"].append({"hook": manifest["script"]["hook"], "at": manifest["created_at"]})


def finalize_upload(state: dict[str, Any], content_id: str, result: dict[str, Any]) -> None:
    if content_id in state.get("uploads", {}):
        existing = state["uploads"][content_id]
        if existing.get("youtube_video_id") == result.get("youtube_video_id"):
            existing["privacy_status"] = result.get("privacy_status", existing.get("privacy_status"))
            return
        raise ValueError("content already has a different upload record")
    result = {**result, "recorded_at": datetime.now(timezone.utc).isoformat()}
    state["uploads"][content_id] = result
    if content_id in state.get("pending", {}):
        state["pending"][content_id]["status"] = "published"
