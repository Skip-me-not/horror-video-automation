from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from providers import local_assets, user_urls, wikimedia
from src.kpop_automation.face_crop import prepare_vertical, video_focus_x


def prepare(root: Path, job: dict[str, Any], output: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Return only media with a recorded reuse basis; failure falls back to typography."""
    mode = str(job["media"]).strip()
    cache = root / "cache" / "media"
    candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    if mode.casefold() == "automatic":
        try:
            candidates.extend(local_assets.search(root, job["person"]))
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f"local approved assets: {exc}")
        if os.getenv("WIKIMEDIA_MEDIA_ENABLED", "false").casefold() == "true":
            try:
                candidates.extend(wikimedia.search(job["person"], root, cache))
            except Exception as exc:
                errors.append(f"Wikimedia unavailable: {exc}")
    elif mode.startswith("asset:"):
        candidates.extend(local_assets.search(root, job["person"], mode[6:].strip()))
        if not candidates:
            errors.append("requested local asset is not approved or missing")
    else:
        for url in mode.splitlines():
            url = url.strip()
            if not url:
                continue
            try:
                candidates.append(user_urls.download(url, root, cache))
            except Exception as exc:
                errors.append(f"requested URL skipped: {exc}")
    prepared: list[dict[str, Any]] = []
    for index, item in enumerate(candidates[:12]):
        try:
            path = Path(item["path"])
            if item["type"] == "image":
                vertical = output / "media" / f"{index:03d}-vertical.png"
                prepare_vertical(path, vertical, index, str(item.get("attribution", "")))
                render_path = vertical
            elif item["type"] == "video":
                render_path = path
            else:
                raise ValueError("unsupported asset type")
            prepared.append({**item, "path": str(render_path), "approved": True,
                             "focus_x": video_focus_x(path) if item["type"] == "video" else 0.5})
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"asset {item.get('id', index)} skipped: {exc}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "media_manifest.json").write_text(
        json.dumps({"assets": prepared, "errors": errors, "fallback": not bool(prepared)}, indent=2),
        encoding="utf-8",
    )
    return prepared, errors
