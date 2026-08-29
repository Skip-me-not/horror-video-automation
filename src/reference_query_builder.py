from __future__ import annotations

from typing import Any

from .captions import Caption


def build_reference_queries(captions: list[Caption], mappings: dict[str, list[str]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    last_time = -999.0
    used: set[tuple[str, str]] = set()
    for caption in captions:
        lowered = caption.text.casefold()
        for keyword, queries in mappings.items():
            if keyword.casefold() not in lowered or caption.start - last_time < 5.0:
                continue
            query = queries[len(events) % len(queries)]
            key = (keyword, query)
            if key in used:
                continue
            events.append({"time": round(caption.start, 3), "keyword": keyword,
                           "query": query, "transcript": caption.text})
            used.add(key)
            last_time = caption.start
            break
    return events
