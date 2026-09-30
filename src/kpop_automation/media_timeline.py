from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .face_crop import prepare_vertical, video_focus_x
from .media_downloader import download_approved
from .models import Topic
from .reddit_media import discover


def _save_source_records(path: Path, current: list[dict[str, Any]]) -> None:
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    except (OSError, ValueError):
        existing = []
    by_id = {item["asset_id"]: item for item in existing if isinstance(item, dict) and item.get("asset_id")}
    by_id.update({item["asset_id"]: item for item in current})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(by_id.values())[-1000:], ensure_ascii=False, indent=2), encoding="utf-8")


def build_timeline(root: Path, topic: Topic, config: dict[str, Any],
                   cards: list[dict[str, Any]], story_id: str,
                   discover_live: bool = True) -> tuple[list[dict[str, Any]], list[str]]:
    """Replace a few original graphics with explicitly approved Reddit-discovered media."""
    if discover_live:
        try:
            candidates, errors = discover(topic, root, config)
        except Exception as exc:
            candidates, errors = [], [f"Reddit discovery unavailable: {exc}"]
    else:
        candidates, errors = [], ["fictional fixture does not query Reddit"]
    source_path = root / "data" / "media_sources.json"
    _save_source_records(source_path, candidates)
    usable: list[dict[str, Any]] = []
    for candidate in candidates:
        if not candidate["approved_for_use"]:
            continue
        kind = candidate["media_type"]
        limit = 5 if kind == "video" else 10
        if sum(item["type"] == kind for item in usable) >= limit:
            continue
        try:
            local = download_approved(candidate, root / "output" / "media" / story_id)
            if local["media_type"] == "image":
                prepared = prepare_vertical(Path(local["local_path"]),
                                            root / "output" / "media" / story_id / f"{local['asset_id']}-vertical.png",
                                            len(usable), local["reddit_username"])
                render_path = prepared["path"]
            else:
                render_path = local["local_path"]
            usable.append({"id": local["asset_id"], "path": render_path, "type": local["media_type"],
                           "license": local["license_or_permission"], "approved": True,
                           "source_url": local["original_source_url"], "reddit_post_url": local["reddit_post_url"],
                           "permission_evidence_url": local["permission_evidence_url"],
                           "attribution": f"u/{local['reddit_username']} via r/{local['subreddit']}",
                           "focus_x": video_focus_x(Path(render_path)) if local["media_type"] == "video" else 0.5,
                           "segment_seconds": 3.0 if local["media_type"] == "video" else 0.0})
            candidate.update({"downloaded_at": local["downloaded_at"], "local_path": local["local_path"]})
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"approved asset {candidate['asset_id']} skipped: {exc}")
    _save_source_records(source_path, candidates)
    timeline = [dict(card, type="image") for card in cards]
    positions = list(range(2, max(2, len(timeline) - 1), 2))
    for asset, position in zip(usable[:len(positions)], positions):
        timeline[position] = asset
    manifest = {"story_id": story_id, "topic_id": topic.topic_id, "sources": [item.to_dict() for item in topic.sources],
                "reddit_candidates": candidates, "timeline": timeline, "errors": errors}
    manifest_path = root / "output" / "manifests" / f"{story_id}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return timeline, errors
