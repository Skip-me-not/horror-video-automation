#!/usr/bin/env python3
"""Merge Reddit rotation state after concurrent GitHub Actions runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def unique_tail(left: list[Any], right: list[Any], limit: int) -> list[str]:
    merged: list[str] = []
    for value in [*left, *right]:
        text = str(value)
        if text in merged:
            merged.remove(text)
        merged.append(text)
    return merged[-limit:]


def recent_video_tail(left: list[Any], right: list[Any], limit: int = 30) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for value in [*left, *right]:
        if not isinstance(value, dict) or not value.get("video_id"):
            continue
        merged = [item for item in merged if item.get("video_id") != value["video_id"]]
        merged.append(value)
    return merged[-limit:]


def merge_states(current: dict[str, Any], rendered: dict[str, Any]) -> dict[str, Any]:
    if current.get("version", 1) != 1 or rendered.get("version", 1) != 1:
        raise RuntimeError("Only version 1 Reddit state can be merged")
    return {
        "version": 1,
        "used_fact_urls": unique_tail(
            current.get("used_fact_urls", []), rendered.get("used_fact_urls", []), 500
        ),
        "used_clip_urls": unique_tail(
            current.get("used_clip_urls", []), rendered.get("used_clip_urls", []), 500
        ),
        "idol_history": unique_tail(
            current.get("idol_history", []), rendered.get("idol_history", []), 60
        ),
        "recent_videos": recent_video_tail(
            current.get("recent_videos", []), rendered.get("recent_videos", []), 30
        ),
    }


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "used_fact_urls": [], "used_clip_urls": [], "idol_history": [], "recent_videos": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"State file must contain an object: {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current", type=Path)
    parser.add_argument("rendered", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    merged = merge_states(read_state(args.current), read_state(args.rendered))
    args.output.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
