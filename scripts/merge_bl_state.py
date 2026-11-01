#!/usr/bin/env python3
"""Merge independently produced BL state snapshots after a concurrent Git fetch."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from scripts.bl_engine import default_state, read_json, write_json_atomic


def unique(values: list[Any], key) -> list[Any]:
    output, seen = [], set()
    for value in values:
        identity = key(value)
        if identity in seen:
            continue
        seen.add(identity)
        output.append(value)
    return output


def merge_history(left: list[Any], right: list[Any]) -> list[Any]:
    """Preserve repeated rotations while joining snapshots with a common prefix."""
    shared = 0
    for old, new in zip(left, right):
        if old != new:
            break
        shared += 1
    return (left + right[shared:])[-250:]


def merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    result = default_state()
    for name in ("template_history", "hook_history", "layout_history", "title_pattern_history"):
        result[name] = merge_history(list(left.get(name, [])), list(right.get(name, [])))
    for source in (left.get("category_counts", {}), right.get("category_counts", {})):
        for key, value in source.items():
            result["category_counts"][key] = max(int(value), result["category_counts"].get(key, 0))
    result["published"] = unique(list(left.get("published", [])) + list(right.get("published", [])), key=lambda item: item.get("story_id"))[-250:]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_json_atomic(args.output, merge(read_json(args.base), read_json(args.snapshot)))


if __name__ == "__main__":
    main()
