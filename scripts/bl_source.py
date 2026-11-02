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
from urllib.parse import urljoin, urlparse, urlunparse

import requests

from scripts.bl_engine import BLEngineError, CONFIG_PATH, ROOT, load_state, normalized_url, read_json, verification_result, write_json_atomic
from scripts.reddit_source import RedditClient, RedditSourceError, parse_subreddits, reddit_post_url

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
    ("comeback", ("reunion", "reunites", "comeback", "welcome back")),
    ("milestone", ("milestone", "ranking", "million views", "record")),
]

NEWS_TERMS = ("announce", "announcement", "official pilot", "official trailer", "teaser", "cast", "casting", "premiere", "release date", "fanmeeting", "fan meeting", "interview", "award", "event", "lineup", "press conference")
NOISE_PATTERN = re.compile(r"(?:\[bts\]|\[?recap\]?|\blive!?\b|behind\s+the\s+scenes|full\s+episode|\bep\.?\s*\d+|\bepisode\s*\d+|\bpart\s*\d+|\bost\b|official\s+mv|music\s+video|dance\s+practice|reaction)", re.I)
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
DEFAULT_BL_SUBREDDITS = ("boyslove", "ThaiBL", "GMMTV")
DEFAULT_BL_QUERIES = ("BL",)


def strip_markup(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def validated_feed_url(value: str) -> str:
    """Validate a feed endpoint without discarding functional query parameters."""
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return ""
    return urlunparse(("https", parsed.netloc.lower(), parsed.path or "/", "", parsed.query, ""))


def classify(headline: str) -> str:
    lowered = headline.casefold()
    for category, terms in CATEGORY_TERMS:
        if any(term in lowered for term in terms):
            return category
    return "general_entertainment"


def feed_relevance(headline: str, category: str) -> int:
    lowered = headline.casefold()
    score = 50 if category != "general_entertainment" else 0
    score += 20 * sum(term in lowered for term in NEWS_TERMS)
    if NOISE_PATTERN.search(headline):
        score -= 200
    return score


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
        media_description = node.find(".//{*}description")
        thumbnail = node.find(".//{*}thumbnail")
        entries.append({
            "headline": text("title"),
            "summary": text("description", "summary", "content") or strip_markup(media_description.text if media_description is not None else ""),
            "url": normalized_url(urljoin(base_url, link)),
            "date": text("pubDate", "published", "updated"),
            "thumbnail": (thumbnail.attrib.get("url", "") if thumbnail is not None else ""),
        })
    return [entry for entry in entries if entry["headline"] and entry["url"]]


def display_date(value: str) -> str:
    match = re.search(r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?\b", value, re.I)
    if match:
        return match.group(0)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except (TypeError, ValueError):
        return value or "the announced date"


def clean_series_title(headline: str) -> str:
    value = re.sub(r"^\s*\[[^]]+\]\s*", "", headline).strip()
    value = re.sub(r"^\s*LIVE!?\s*[:|-]?\s*", "", value, flags=re.I).strip()
    value = re.sub(r"\s*[|︱｜]\s*[^|︱｜]+$", "", value).strip()
    value = re.sub(r"\s*(?:premieres?|airs?|releases?)\s+(?:on\s+)?(?:[A-Z][a-z]{2,8}\s+\d{1,2}(?:,\s*\d{4})?).*$", "", value, flags=re.I).strip(" -:!")
    value = value.title() if value.isupper() else value
    return value or headline


def retention_hook(category: str, series: str) -> str:
    hooks = {
        "release_date": f"{series} fans—this is the date you were waiting for.",
        "trailer_release": f"Wait—{series} just dropped an official first look.",
        "casting": f"This casting is official—here is what just got confirmed for {series}.",
        "series_announcement": f"A new BL alert just dropped: {series}.",
        "fan_meeting": f"{series} fans, this official event update is for you.",
        "comeback": f"They are back—{series} just made it official.",
        "award": f"{series} just reached a moment fans will want to see.",
    }
    return hooks.get(category, f"Stop scrolling—{series} just got an official update.")


def concise_english_summary(summary: str, category: str, series: str, source_name: str) -> str:
    cleaned = re.sub(r"https?://\S+|\S+@\S+", " ", strip_markup(summary))
    candidates = re.split(r"(?<=[.!?])\s+|[\n|]", cleaned)
    blocked = ("subscribe", "membership", "super thanks", "contact", "advertis")
    for candidate in candidates:
        candidate = re.sub(r"\s+", " ", candidate).strip(" -—")
        letters = [character for character in candidate if character.isalpha()]
        english = sum(character.isascii() for character in letters)
        if 24 <= len(candidate) <= 180 and letters and english / len(letters) >= 0.85 and not any(term in candidate.casefold() for term in blocked):
            return candidate
    label = category.replace("_", " ")
    return f"The verified post gives fans a direct look at the {label} for {series}."


def youtube_assets(entry: dict[str, str], *, official: bool) -> list[dict[str, Any]]:
    parsed = urlparse(entry.get("url", ""))
    if parsed.netloc.casefold() not in YOUTUBE_HOSTS:
        thumbnail = entry.get("thumbnail", "")
        return [{"url": thumbnail, "authorized": official, "role": "source_thumbnail"}] if thumbnail.startswith("https://") else []
    # Use several short moments from the same verified source instead of holding one frame.
    assets: list[dict[str, Any]] = [
        {"url": entry["url"], "authorized": official, "role": "source_video", "clip_start": start, "optional": True}
        for start in (0, 4, 9, 14)
    ]
    thumbnail = entry.get("thumbnail", "")
    if thumbnail.startswith("https://"):
        assets.append({"url": thumbnail, "authorized": official, "role": "source_thumbnail"})
    return assets


def story_from_entry(entry: dict[str, str], feed: dict[str, Any]) -> dict[str, Any]:
    headline, summary = entry["headline"], entry["summary"] or entry["headline"]
    category = classify(headline)
    relevance = feed_relevance(headline, category)
    series = clean_series_title(headline)
    announced_date = display_date(headline if re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", headline, re.I) else entry["date"])
    source_name = str(feed.get("name") or "the official channel")
    category_label = "update" if category == "general_entertainment" else category.replace("_", " ")
    summary_line = concise_english_summary(summary, category, series, source_name)
    script_points = [
        f"{source_name} posted the official {category_label}.",
        summary_line,
    ]
    if category == "release_date":
        script_points.append(f"The date fans need to remember is {announced_date}.")
    elif category == "trailer_release":
        script_points.append("The official preview is live now, so the first real clues are finally here.")
    elif category == "casting":
        script_points.append("This is the confirmed lineup, not a fan rumor.")
    story = {
        "story_id": "feed-" + __import__("hashlib").sha256(entry["url"].encode()).hexdigest()[:16],
        "category": category, "headline": headline, "event": headline, "context": summary,
        "detail": summary, "date": entry["date"] or datetime.now(timezone.utc).date().isoformat(),
        "source_name": source_name,
        "company": str(feed.get("company") or feed.get("name") or "the publisher"),
        "series": series, "actor": str(feed.get("default_actor") or "the announced cast"),
        "actor_2": str(feed.get("default_actor_2") or "the co-star"),
        "network": str(feed.get("network") or feed.get("name") or "the announced platform"),
        "country": str(feed.get("country") or "Asian"), "release_date": announced_date,
        "venue": str(feed.get("venue") or "the announced venue"), "award": headline,
        "achievement": headline, "official_statement": summary,
        "official_confirmation": feed.get("source_type") == "official",
        "sources": [{"type": feed.get("source_type", "unknown"), "name": feed.get("name", "Configured source"), "url": entry["url"], "date": entry["date"]}],
        "assets": youtube_assets(entry, official=feed.get("source_type") == "official"), "feed_relevance": relevance,
        "script_hook": retention_hook(category, series),
        "script_points": script_points,
        "script_cta": "Would you watch this one?",
        "collected_at": datetime.now(timezone.utc).isoformat(),
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
        url = validated_feed_url(feed.get("url", ""))
        if not url or feed.get("source_type") not in config["verification"]["scores"]:
            raise BLEngineError("Every configured feed needs a valid URL and source_type")
        response = session.get(url, timeout=(10, 30))
        response.raise_for_status()
        feed_stories = [story_from_entry(entry, feed) for entry in feed_entries(response.content, url)[:20]]
        stories.extend(story for story in feed_stories if story["feed_relevance"] >= 0)
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
            eligible.append((result["score"], story.get("date", ""), int(story.get("feed_relevance", 0)), story.get("story_id", ""), story, origin))
    if not eligible:
        raise BLEngineError("No unpublished auto-publishable queue or feed story is available")
    _, _, _, _, story, origin = max(eligible, key=lambda item: item[:4])
    return story, origin


def collect_ranked(count: int = 6, *, allow_review: bool = False) -> tuple[list[dict[str, Any]], str]:
    """Return the strongest unused feed stories, ranked #1 first."""
    config = read_json(CONFIG_PATH)
    state = load_state()
    used_ids = {item.get("story_id") for item in state.get("published", [])}
    used_urls = {url for item in state.get("published", []) for url in item.get("source_urls", [])}
    candidates = [story for story in collect_from_feeds(config)
                  if story.get("story_id") not in used_ids
                  and not ({normalized_url(item.get("url", "")) for item in story.get("sources", [])} & used_urls)]
    eligible = []
    for story in candidates:
        result = verification_result(story, config)
        if result["decision"] == "auto_publish" or allow_review:
            eligible.append((story.get("date", ""), int(story.get("feed_relevance", 0)), story.get("story_id", ""), story))
    eligible.sort(key=lambda item: item[:3], reverse=True)
    selected = [item[3] for item in eligible[:count]]
    if len(selected) < count:
        raise BLEngineError(f"Need {count} unused verified BL source videos, found {len(selected)}")
    return selected, "configured_feeds_ranked"


def reddit_story(post: dict[str, Any]) -> dict[str, Any]:
    """Convert one safe, Reddit-hosted BL clip into the ranked-renderer schema."""
    title = strip_markup(str(post.get("title") or ""))
    source_url = reddit_post_url(str(post.get("permalink") or ""))
    created = float(post.get("created_utc") or 0)
    published = datetime.fromtimestamp(created, timezone.utc).date().isoformat() if created else datetime.now(timezone.utc).date().isoformat()
    return {
        "story_id": "reddit-" + str(post.get("id") or __import__("hashlib").sha256(source_url.encode()).hexdigest()[:16]),
        "category": "general_entertainment",
        "headline": title,
        "event": title,
        "context": f"A public BL community video post in r/{post.get('subreddit') or 'boyslove'}.",
        "detail": title,
        "date": published,
        "source_name": f"r/{post.get('subreddit') or 'boyslove'}",
        "company": "Reddit community",
        "series": title,
        "actor": "the featured cast",
        "actor_2": "the co-star",
        "network": "the featured series",
        "country": "Asian",
        "release_date": published,
        "venue": "the featured scene",
        "award": title,
        "achievement": title,
        "official_statement": title,
        "official_confirmation": False,
        "sources": [{
            "type": "reddit",
            "name": f"Reddit r/{post.get('subreddit') or 'boyslove'}",
            "url": source_url,
            "date": published,
        }],
        "assets": [{
            "url": str(post["video_url"]),
            "role": "reddit_source_video",
            "source_url": source_url,
        }],
        "reddit_score": int(post.get("score") or 0),
        "reddit_comments": int(post.get("num_comments") or 0),
        "script_hook": "Top BL moments fans could not stop replaying.",
        "script_points": [title],
        "script_cta": "Which moment is your number one?",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def collect_reddit_ranked(count: int = 6) -> tuple[list[dict[str, Any]], str]:
    """Collect distinct public Reddit-hosted BL videos without cookies or API keys."""
    state = load_state()
    used_urls = {
        normalized_url(url)
        for item in state.get("published", [])
        for url in item.get("source_urls", [])
    }
    subreddits = parse_subreddits(os.environ.get("BL_REDDIT_SUBREDDITS", ",".join(DEFAULT_BL_SUBREDDITS)))
    queries = [value.strip() for value in os.environ.get("BL_REDDIT_QUERIES", "|".join(DEFAULT_BL_QUERIES)).split("|") if value.strip()]
    client = RedditClient(user_agent=os.environ.get("REDDIT_USER_AGENT", "github:Lululala-BL-Shorts:v3.0 (public media collector)"))
    candidates: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for subreddit in subreddits:
        for query in queries:
            try:
                posts = client.search(subreddit, query, limit=100, require_video=True)
            except RedditSourceError as exc:
                errors.append(str(exc))
                continue
            for post in posts:
                source_url = reddit_post_url(str(post.get("permalink") or "")) if post.get("permalink") else ""
                title = strip_markup(str(post.get("title") or ""))
                if not (
                    post.get("id")
                    and source_url
                    and normalized_url(source_url) not in used_urls
                    and str(post.get("video_url") or "").startswith("https://v.redd.it/")
                    and not post.get("over_18")
                    and not post.get("stickied")
                    and not post.get("removed")
                    and 3 <= len(title.split()) <= 32
                ):
                    continue
                candidates[str(post["id"])] = post
    ranked = sorted(
        candidates.values(),
        key=lambda post: (
            int(post.get("score") or 0) + 3 * int(post.get("num_comments") or 0),
            float(post.get("created_utc") or 0),
            str(post.get("id") or ""),
        ),
        reverse=True,
    )
    if len(ranked) < count:
        detail = f" Last fetch error: {errors[-1]}" if errors else ""
        raise BLEngineError(f"Need {count} unused public Reddit-hosted BL videos, found {len(ranked)}.{detail}")
    return [reddit_story(post) for post in ranked[:count]], "public_reddit_bl_videos"


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
