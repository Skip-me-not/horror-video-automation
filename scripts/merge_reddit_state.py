from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON array")
    return [item for item in payload if isinstance(item, dict)]


def _history_key(item: dict[str, Any]) -> tuple[str, str]:
    for field in ("source_video_id", "youtube_video_id", "video_hash"):
        if item.get(field):
            return field, str(item[field])
    return "record", json.dumps(item, sort_keys=True, ensure_ascii=False)


def merge_history(remote: list[dict[str, Any]], incoming: list[dict[str, Any]],
                  limit: int = 300) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in [*remote, *incoming]:
        merged[_history_key(item)] = item
    return list(merged.values())[-limit:]


def merge_pool(remote: list[dict[str, Any]], incoming: list[dict[str, Any]],
               used_ids: set[str], limit: int = 160) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in [*remote, *incoming]:
        post_id = str(item.get("post_id") or "")
        if post_id and post_id not in used_ids:
            merged[post_id] = item
    return list(merged.values())[-limit:]


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge concurrent Reddit pipeline state safely.")
    parser.add_argument("--incoming-history", type=Path, required=True)
    parser.add_argument("--incoming-pool", type=Path, required=True)
    parser.add_argument("--history", type=Path, default=Path("data/history.json"))
    parser.add_argument("--pool", type=Path, default=Path("data/celebrity_source_pool.json"))
    args = parser.parse_args()

    history = merge_history(_load_list(args.history), _load_list(args.incoming_history))
    used_ids = {str(item["source_video_id"]) for item in history if item.get("source_video_id")}
    pool = merge_pool(_load_list(args.pool), _load_list(args.incoming_pool), used_ids)
    args.history.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.pool.write_text(json.dumps(pool, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
