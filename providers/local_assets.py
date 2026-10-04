from __future__ import annotations

from pathlib import Path
from typing import Any

from src.kpop_automation.assets import load_approved_assets


def search(root: Path, person: str, asset_id: str = "") -> list[dict[str, Any]]:
    results = []
    for item in load_approved_assets(root).values():
        if asset_id and item["id"] != asset_id:
            continue
        tags = " ".join(str(value) for value in (item.get("person") or "", item.get("tags") or "")).strip()
        if not asset_id and (not tags or person.casefold() not in tags.casefold()):
            continue
        path = Path(item["resolved_path"])
        kind = "video" if path.suffix.casefold() in {".mp4", ".mov", ".webm"} else "image"
        results.append({"id": item["id"], "path": str(path), "type": kind,
                        "source_url": item["source_url"], "license": item["license"],
                        "attribution": item["attribution"], "permission_evidence_url": item["source_url"]})
    return results
