#!/usr/bin/env python3
"""Collect structured BL stories from a queue or explicitly configured RSS/Atom feeds."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from scripts.bl_engine import BLEngineError, CONFIG_PATH, ROOT, load_state, normalized_url, read_json, verification_result, write_json_atomic

QUEUE_DIR = ROOT / "data" / "queue"
COLLECTED_DIR = ROOT / "data" / "collected"

CATEGORY_TERMS = [
    ("clarification", ("clarifies", "clarification", "correction", "corrects")),
    ("release_date", ("release date", "premieres", "premiere date", "airs on")),
    ("trailer_release", ("trailer", "teaser", "first look")),
    ("casting", ("cast", "casting", "stars", "pairing")),
    ("series_announcement", ("new series", "announces series", "drama adaptation")),
    ("fan_meeting", ("fan meeting", "fanmeet", "fan event")),
    ("award", ("award", "nomination", "nominated", "wins")),
    ("interview", ("interview", "speaks about", "opens up")),
    ("agency_update", ("agency", "contract", "management")),
    ("collaboration", ("collaboration", "teams up", "partnership")),
    ("comeback", ("reunion", "reunites", "comeback")),
    ("milestone", ("milestone", "ranking", "million views", "record")),
]


def strip_markup(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def classify(headline: str) -> str:
    lowered = headline.casefold()
    for category, terms in CATEGORY_TERMS:
        if any(term in lowered for term in terms):
            return category
    return "general_entertainment"


def feed_entries(content: bytes, base_url: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise BLEngineError(f"Invalid RSS/Atom feed {base_url}: {exc}") from exc
    entries = []
    nodes = root.findall(".//item") or root.findall(".//{*}entry")
    for node in nodes:
        def text(*names: str) -> str:
            for name in names:
                element = node.find(name) or node.find("{*}" + name)
                if element is not None and element.text:
                    return strip_markup(element.text)
            return ""
        link = text("link")
        if not link:
            element = node.find("{*}link")
            link = (element.attrib.get("href", "") if element is not None else "")
        entries.append({
            "headline": text("title"), "summary": text("description", "summary", "content"),
            "url": normalized_url(urljoin(base_url, link)), "date": text("pubDate", "published", "updated"),
        })
    return [entry for entry in entries if entry["headline"] and entry["url"]]


def story_from_entry(entry: dict[str, str], feed: dict[str, Any]) -> dict[str, Any]:
    headline, summary = entry["headline"], entry["summary"] or entry["headline"]
    category = classify(headline)
    story = {
        "story_id": "feed-" + __import__("hashlib").sha256(entry["url"].encode()).hexdigest()[:16],
        "category": category, "headline": headline, "event": headline, "context": summary,
        "detail": summary, "date": entry["date"] or datetime.now(timezone.utc).date().isoformat(),
        "source_name": str(feed.get("name") or "Configured source"),
        "company": str(feed.get("company") or feed.get("name") or "the publisher"),
        "series": headline, "actor": str(feed.get("default_actor") or "the announced cast"),
        "actor_2": str(feed.get("default_actor_2") or "the co-star"),
        "network": str(feed.get("network") or feed.get("name") or "the announced platform"),
        "country": str(feed.get("country") or "Asian"), "release_date": entry["date"] or "the announced date",
        "venue": str(feed.get("venue") or "the announced venue"), "award": headline,
        "achievement": headline, "official_statement": summary,
        "official_confirmation": feed.get("source_type") == "official",
        "sources": [{"type": feed.get("source_type", "unknown"), "name": feed.get("name", "Configured source"), "url": entry["url"], "date": entry["date"]}],
        "assets": [], "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    return story


def collect_from_feeds(config: dict[str, Any]) -> list[dict[str, Any]]:
    stories = []
    session = requests.Session()
    session.headers["User-Agent"] = "Lululala-BL-News-Automation/2.0"
    feeds = config.get("feeds", [])
    override = os.environ.get("BL_SOURCE_FEEDS_JSON", "").strip()
    if override:
        try:
            feeds = json.loads(override)
        except json.JSONDecodeError as exc:
            raise BLEngineError(f"BL_SOURCE_FEEDS_JSON is invalid JSON: {exc}") from exc
        if not isinstance(feeds, list):
            raise BLEngineError("BL_SOURCE_FEEDS_JSON must be a JSON array")
    for feed in feeds:
        if not feed.get("enabled", True):
            continue
        url = normalized_url(feed.get("url", ""))
        if not url or feed.get("source_type") not in config["verification"]["scores"]:
            raise BLEngineError("Every configured feed needs a valid URL and source_type")
        response = session.get(url, timeout=(10, 30))
        response.raise_for_status()
        stories.extend(story_from_entry(entry, feed) for entry in feed_entries(response.content, url)[:20])
    return stories


def queue_stories(queue_dir: Path = QUEUE_DIR) -> list[tuple[Path, dict[str, Any]]]:
    values = []
    for path in sorted(queue_dir.glob("*.json")) if queue_dir.exists() else []:
        if path.name.startswith("sample-"):
            continue
        payload = read_json(path)
        if isinstance(payload, dict):
            values.append((path, payload))
    return values


def collect_one(*, allow_review: bool = False) -> tuple[dict[str, Any], str]:
    config = read_json(CONFIG_PATH)
    state = load_state()
    published = {item.get("story_id") for item in state.get("published", [])}
    candidates = [(story, str(path)) for path, story in queue_stories()]
    if not candidates:
        candidates = [(story, "configured_feed") for story in collect_from_feeds(config)]
    eligible = []
    for story, origin in candidates:
        if story.get("story_id") in published:
            continue
        result = verification_result(story, config)
        if result["decision"] == "auto_publish" or allow_review:
            eligible.append((result["score"], story.get("story_id", ""), story, origin))
    if not eligible:
        raise BLEngineError("No unpublished auto-publishable queue or feed story is available")
    _, _, story, origin = max(eligible, key=lambda item: (item[0], item[1]))
    return story, origin


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "story.json")
    parser.add_argument("--allow-review", action="store_true")
    args = parser.parse_args()
    story, origin = collect_one(allow_review=args.allow_review)
    write_json_atomic(args.output, story)
    print(f"Collected {story.get('story_id')} from {origin}")


if __name__ == "__main__":
    try:
        main()
    except (BLEngineError, requests.RequestException) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
