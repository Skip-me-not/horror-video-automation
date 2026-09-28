from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Topic

BLOCKED_TERMS = ("leak", "paparazzi", "private", "full episode", "full drama", "full movie",
                 "music video", "official mv", "full performance", "fancam", "watermark", "stolen")
APPROVED_LICENSES = {"CC0-1.0", "CC-BY-4.0", "PUBLIC-DOMAIN", "OWNED", "PERMISSION-GRANTED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _asset_id(post_id: str, media_url: str) -> str:
    return hashlib.sha256(f"{post_id}|{media_url}".encode()).hexdigest()[:20]


def risk_score(post: dict[str, Any], original_source_url: str = "") -> int:
    title = str(post.get("title", "")).casefold()
    score = 10
    if post.get("over_18") or post.get("spoiler"):
        score += 65
    score += sum(35 for term in BLOCKED_TERMS if term in title)
    if not original_source_url:
        score += 45
    if post.get("is_video"):
        score += 10
    if post.get("crosspost_parent"):
        score += 15
    return min(100, score)


def load_approvals(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"assets": []}
    approvals: dict[str, dict[str, Any]] = {}
    for item in payload.get("assets", []):
        if (item.get("asset_id") and item.get("license") in APPROVED_LICENSES
                and str(item.get("original_source_url", "")).startswith("https://")
                and str(item.get("permission_evidence_url", "")).startswith("https://")
                and item.get("approved_by") and item.get("approved_at")):
            approvals[str(item["asset_id"])] = item
    return approvals


def candidate_from_post(post: dict[str, Any], approval: dict[str, Any] | None = None,
                        threshold: int = 35) -> dict[str, Any] | None:
    media = post.get("secure_media") or post.get("media") or {}
    reddit_video = media.get("reddit_video") or {}
    media_url = str(reddit_video.get("fallback_url") or "") if post.get("is_video") else str(post.get("url_overridden_by_dest") or post.get("url") or "")
    media_type = "video" if post.get("is_video") else "image"
    if media_type == "image" and urlsplit(media_url).netloc.lower() not in {"i.redd.it", "preview.redd.it"}:
        return None
    if media_type == "video" and urlsplit(media_url).netloc.lower() != "v.redd.it":
        return None
    if not media_url.startswith("https://"):
        return None
    post_id = str(post.get("id", ""))
    if not post_id:
        return None
    asset_id = _asset_id(post_id, media_url)
    original_source_url = str((approval or {}).get("original_source_url") or "")
    risk = risk_score(post, original_source_url)
    approved = bool(approval and approval.get("asset_id") == asset_id
                    and approval.get("license") in APPROVED_LICENSES
                    and approval.get("permission_evidence_url") and risk <= threshold)
    posted_at = datetime.fromtimestamp(float(post.get("created_utc") or 0), timezone.utc).isoformat()
    return {
        "asset_id": asset_id, "celebrity": "", "reddit_post_url": "https://www.reddit.com" + str(post.get("permalink") or ""),
        "subreddit": str(post.get("subreddit") or ""), "reddit_username": str(post.get("author") or ""),
        "post_title": str(post.get("title") or ""), "media_url": media_url, "media_type": media_type,
        "original_source_url": original_source_url,
        "license_or_permission": str((approval or {}).get("license") or ""),
        "permission_evidence_url": str((approval or {}).get("permission_evidence_url") or ""),
        "posted_at": posted_at, "downloaded_at": "", "risk_score": risk,
        "approved_for_use": approved,
    }


def _token(session: requests.Session, client_id: str, client_secret: str, user_agent: str) -> str:
    response = session.post("https://www.reddit.com/api/v1/access_token",
                            auth=(client_id, client_secret), data={"grant_type": "client_credentials"},
                            headers={"User-Agent": user_agent}, timeout=15)
    response.raise_for_status()
    return str(response.json()["access_token"])


def discover(topic: Topic, root: Path, config: dict[str, Any],
             session: requests.Session | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Use official OAuth search only; missing credentials yield an empty, safe fallback."""
    reddit = config.get("reddit", {})
    credentials = (os.getenv("REDDIT_CLIENT_ID", ""), os.getenv("REDDIT_CLIENT_SECRET", ""),
                   os.getenv("REDDIT_USER_AGENT", ""))
    if not all(credentials):
        return [], ["Reddit OAuth credentials absent; using original graphics only"]
    session = session or requests.Session()
    approvals = load_approvals(root / "config" / "reddit_media_approvals.json")
    cache_path = root / "data" / "reddit_search_cache.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        stored = cache.get(topic.topic_id, {})
        fetched = datetime.fromisoformat(stored.get("fetched_at", ""))
        if fetched.tzinfo and datetime.now(timezone.utc) - fetched < timedelta(hours=6):
            cached = []
            for item in stored.get("candidates", []):
                approval = approvals.get(item["asset_id"], {})
                refreshed = {**item, "original_source_url": approval.get("original_source_url", ""),
                             "license_or_permission": approval.get("license", ""),
                             "permission_evidence_url": approval.get("permission_evidence_url", "")}
                previous_unknown = not bool(item.get("original_source_url"))
                current_unknown = not bool(approval.get("original_source_url"))
                refreshed["risk_score"] = max(0, min(100, int(item["risk_score"]) + 45 * (int(current_unknown) - int(previous_unknown))))
                refreshed["approved_for_use"] = bool(approval and refreshed["risk_score"] <= int(reddit.get("max_risk_score", 35)))
                cached.append(refreshed)
            return cached, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        cache = {}
    adapter = HTTPAdapter(max_retries=Retry(total=2, backoff_factor=1,
                                            status_forcelist=[500, 502, 503, 504], allowed_methods=["GET", "POST"]))
    session.mount("https://", adapter)
    user_agent = credentials[2]
    token = _token(session, credentials[0], credentials[1], user_agent)
    terms = re.findall(r"[A-Za-z0-9]+", topic.title)
    queries = [topic.entity, f"{topic.entity} {' '.join(terms[-3:])}".strip()]
    entity_words = set(re.findall(r"[a-z0-9]+", topic.entity.casefold()))
    event_words = {word for word in re.findall(r"[a-z0-9]+", topic.title.casefold())
                   if len(word) >= 4 and word not in entity_words
                   and word not in {"with", "from", "that", "this", "their", "news", "latest", "announces"}}
    communities = "+".join(reddit.get("subreddits", ["kpop", "KDRAMA", "KoreanActors"]))
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for query in queries[:2]:
        try:
            response = session.get(f"https://oauth.reddit.com/r/{communities}/search",
                                   params={"q": query, "restrict_sr": "on", "sort": "new", "t": "week", "limit": 20},
                                   headers={"Authorization": f"bearer {token}", "User-Agent": user_agent},
                                   timeout=15)
            if response.status_code == 429:
                errors.append("Reddit rate limit reached; stopping discovery")
                break
            response.raise_for_status()
            for child in response.json().get("data", {}).get("children", []):
                post = child.get("data", {})
                if topic.entity.casefold() not in str(post.get("title", "")).casefold():
                    continue
                post_words = set(re.findall(r"[a-z0-9]+", str(post.get("title", "")).casefold()))
                if event_words and not event_words.intersection(post_words):
                    continue
                provisional = candidate_from_post(post, threshold=int(reddit.get("max_risk_score", 35)))
                if provisional is None or provisional["asset_id"] in seen:
                    continue
                item = candidate_from_post(post, approvals.get(provisional["asset_id"]),
                                           int(reddit.get("max_risk_score", 35)))
                if item:
                    item["celebrity"] = topic.entity
                    results.append(item)
                    seen.add(item["asset_id"])
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append(f"Reddit search failed: {exc}")
        time.sleep(float(reddit.get("request_spacing_seconds", 1.0)))
    cache[topic.topic_id] = {"fetched_at": _now(), "candidates": results}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return results, errors
