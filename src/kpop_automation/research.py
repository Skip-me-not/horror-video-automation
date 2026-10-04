from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import CATEGORIES, SourceRecord

BLOCKED = {"dating rumor", "allegedly dating", "leaked", "private relationship", "unconfirmed rumor"}
CATEGORY_TERMS = {
    "trending_news": ("announces", "comeback", "release", "award", "tour", "concert", "debut"),
    "idol_interactions": ("collaboration", "together", "duet", "friendship", "joins"),
    "funny_relatable": ("funny", "laugh", "variety", "joke", "reaction"),
    "transformation": ("journey", "then and now", "evolution", "career", "milestone"),
    "viral_moments": ("viral", "moment", "trending"),
    "explained_analysis": ("explained", "meaning", "analysis", "concept", "theme"),
    "idol_storytelling": ("trainee", "story", "achievement", "history"),
    "fan_debate": ("fans discuss", "favorite", "ranking", "debate"),
}


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def clean_text(value: str, limit: int = 500) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return " ".join(value.split())[:limit].strip()


def classify(text: str) -> str:
    lowered = text.casefold()
    scores = {category: sum(term in lowered for term in terms) for category, terms in CATEGORY_TERMS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "idol_storytelling"


def _published(entry: dict[str, Any]) -> str:
    raw = str(entry.get("published") or entry.get("updated") or "")
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    return ""


def parse_feed(payload: bytes, source: dict[str, Any], entities: list[str], accessed_at: str) -> list[SourceRecord]:
    feed = feedparser.parse(payload)
    records: list[SourceRecord] = []
    for entry in feed.entries:
        title = clean_text(str(entry.get("title", "")), 240)
        evidence = clean_text(str(entry.get("summary") or entry.get("description") or ""), 600)
        url = canonical_url(str(entry.get("link", "")))
        combined = f"{title} {evidence}"
        matched = tuple(name for name in entities if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", combined, re.I))
        if not title or not url or not matched or any(term in combined.casefold() for term in BLOCKED):
            continue
        fingerprint = hashlib.sha256(re.sub(r"\W+", " ", combined.casefold()).encode()).hexdigest()
        source_id = hashlib.sha256(url.encode()).hexdigest()[:20]
        records.append(SourceRecord(
            source_id=source_id, title=title, url=url, publisher=str(source["name"]),
            published_at=_published(entry), accessed_at=accessed_at,
            evidence=evidence or title, entities=matched, category=classify(combined),
            reliability=int(source.get("reliability", 1)), source_kind=str(source.get("kind", "news")),
            rights=str(source.get("rights", "facts_only")), fingerprint=fingerprint,
        ))
    return records


def collect(config: dict[str, Any], session: requests.Session | None = None) -> tuple[list[SourceRecord], list[dict[str, str]]]:
    research = config["research"]
    session = session or requests.Session()
    adapter = HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.8,
                                            status_forcelist=[429, 500, 502, 503, 504],
                                            allowed_methods=["GET"]))
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "LululalaResearch/1.0 (+https://github.com/Skip-me-not/horror-video-automation)"})
    now = datetime.now(timezone.utc).isoformat()
    records: list[SourceRecord] = []
    errors: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    seen_fingerprints: set[str] = set()
    for source in research.get("sources", []):
        try:
            response = session.get(source["url"], timeout=int(research.get("timeout_seconds", 20)))
            response.raise_for_status()
            parsed = parse_feed(response.content, source, list(research.get("entities", [])), now)
            for item in parsed:
                if item.url not in seen_urls and item.fingerprint not in seen_fingerprints:
                    records.append(item)
                    seen_urls.add(item.url)
                    seen_fingerprints.add(item.fingerprint)
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append({"source": str(source.get("name", source.get("url", "unknown"))), "error": str(exc)})
    return records, errors
