#!/usr/bin/env python3
"""Remove one successfully uploaded script from the available quote catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def consume_quote(entries: list[dict[str, Any]], quote_id: str) -> list[dict[str, Any]]:
    if quote_id == "manual":
        return entries
    remaining = [entry for entry in entries if str(entry.get("id")) != quote_id]
    if len(remaining) == len(entries):
        raise RuntimeError(f"Quote id is not available to consume: {quote_id}")
    return remaining


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("quote_id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.catalog.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("Quote catalog must be a JSON array")
    remaining = consume_quote(payload, args.quote_id)
    args.output.write_text(
        json.dumps(remaining, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Consumed {args.quote_id}; {len(remaining)} script(s) remain.")


if __name__ == "__main__":
    main()
