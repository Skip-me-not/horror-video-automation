#!/usr/bin/env python3
"""Discover idol discussions and Reddit-hosted clips without Reddit credentials."""

from __future__ import annotations

import html
import json
import math
import random
import re
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
IDOLS_PATH = ROOT / "data" / "idols.json"
PUBLIC_JSON_ROOTS = ("https://www.reddit.com", "https://old.reddit.com")
PULLPUSH_SEARCH_URL = "https://api.pullpush.io/reddit/search/submission/"
ARCTIC_SHIFT_SEARCH_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
DEFAULT_SUBREDDITS = ("kpop", "kpopthoughts", "kpop_uncensored")
IDOL_SUBREDDITS = {
    "jungkook": ("bts7", "bangtan"),
    "jennie": ("BlackPink",),
    "karina": ("Aespa",),
    "wonyoung": ("IVE",),
    "bang chan": ("straykids",),
    "sana": ("twice",),
    "mingyu": ("seventeen",),
    "yeonjun": ("TomorrowByTogether",),
    "chaewon": ("lesserafim",),
    "ningning": ("Aespa",),
    "jihyo": ("twice",),
    "felix": ("straykids",),
}
MIN_FACT_SCORE = 40
MIN_CLIP_SCORE = 20
MAX_POST_TITLE_WORDS = 26
SPECULATION_TERMS = {
    "alleged",
    "apparently",
    "blind item",
    "leak",
    "leaked",
    "maybe",
    "might be",
    "possibly",
    "rumor",
    "rumour",
    "sasaeng",
    "speculation",
    "unconfirmed",
}
VIDEO_HOSTS = ("v.redd.it", "redditmedia.com")


class RedditSourceError(RuntimeError):
    """Public Reddit pages did not provide enough safe source material."""


def web_session(user_agent: str) -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept-Language": "en-US,en;q=0.8",
            "Cache-Control": "no-cache",
        }
    )
    return session


def parse_subreddits(value: str | Iterable[str]) -> list[str]:
    raw = re.split(r"[,+\s]+", value) if isinstance(value, str) else list(value)
    names: list[str] = []
    for item in raw:
        name = str(item).strip().removeprefix("r/")
        if not name:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_]{2,30}", name):
            raise RedditSourceError(f"Invalid subreddit name: {item!r}")
        if name.casefold() not in {existing.casefold() for existing in names}:
            names.append(name)
    if not names:
        raise RedditSourceError("At least one subreddit is required")
    return names


def load_idols(path: Path = IDOLS_PATH) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RedditSourceError(f"Unable to load idol rotation from {path}: {exc}") from exc
    if not isinstance(payload, list):
        raise RedditSourceError("data/idols.json must be a JSON array")
    idols = [re.sub(r"\s+", " ", str(value)).strip() for value in payload]
    idols = [value for value in idols if 2 <= len(value) <= 50]
    if not idols:
        raise RedditSourceError("data/idols.json contains no usable idol names")
    return list(dict.fromkeys(idols))


def choose_idol(
    requested: str,
    *,
    used_idols: Iterable[str] = (),
    rng: random.Random | random.SystemRandom | None = None,
) -> str:
    explicit = re.sub(r"\s+", " ", requested).strip()
    if explicit:
        if len(explicit) > 50 or not re.search(r"[A-Za-z0-9]", explicit):
            raise RedditSourceError("The idol input must be a short searchable name")
        return explicit
    chooser = rng or random.SystemRandom()
    idols = load_idols()
    used = {value.casefold() for value in used_idols}
    fresh = [idol for idol in idols if idol.casefold() not in used]
    return chooser.choice(fresh or idols)


def reddit_post_url(permalink: str) -> str:
    value = str(permalink or "").strip()
    if value.startswith("https://www.reddit.com/"):
        return value
    if not value.startswith("/"):
        raise RedditSourceError("Reddit returned an invalid post permalink")
    return "https://www.reddit.com" + value


def reddit_video_fallback(value: str) -> str:
    raw = html.unescape(str(value or "")).strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not any(
        host == allowed or host.endswith("." + allowed) for allowed in VIDEO_HOSTS
    ):
        return ""
    if host == "v.redd.it" and not parsed.path.casefold().endswith(".mp4"):
        media_id = parsed.path.strip("/").split("/", 1)[0]
        return f"https://v.redd.it/{media_id}/DASH_720.mp4?source=fallback" if media_id else ""
    return raw


def _reddit_video(post: dict[str, Any]) -> dict[str, Any] | None:
    for container_name in ("secure_media", "media"):
        container = post.get(container_name) or {}
        video = container.get("reddit_video") if isinstance(container, dict) else None
        if isinstance(video, dict):
            return video
    crosspost = post.get("crosspost_parent_list") or []
    if crosspost and isinstance(crosspost[0], dict):
        nested = _reddit_video(crosspost[0])
        if nested:
            return nested
    fallback = reddit_video_fallback(str(post.get("url_overridden_by_dest") or post.get("url") or ""))
    if fallback:
        return {"fallback_url": fallback, "duration": post.get("duration") or 30}
    return None


def reddit_video_url(post: dict[str, Any]) -> str:
    video = _reddit_video(post)
    return reddit_video_fallback(str((video or {}).get("fallback_url") or ""))


def normalize_post(raw: dict[str, Any]) -> dict[str, Any]:
    title = re.sub(r"\s+", " ", html.unescape(str(raw.get("title") or ""))).strip()
    video = _reddit_video(raw) or {}
    return {
        "id": str(raw.get("id") or "").removeprefix("t3_"),
        "title": title,
        "author": str(raw.get("author") or "unknown"),
        "subreddit": str(raw.get("subreddit") or "unknown"),
        "score": max(0, int(raw.get("score") or raw.get("ups") or 0)),
        "num_comments": max(0, int(raw.get("num_comments") or 0)),
        "created_utc": float(raw.get("created_utc") or 0),
        "permalink": str(raw.get("permalink") or ""),
        "over_18": bool(raw.get("over_18")),
        "stickied": bool(raw.get("stickied")),
        "is_self": bool(raw.get("is_self")),
        "video_url": reddit_video_fallback(str(video.get("fallback_url") or "")),
        "video_duration": float(video.get("duration") or (30 if video else 0)),
        "removed": str(raw.get("selftext") or "").strip() in {"[removed]", "[deleted]"},
    }


def title_terms(title: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9]+", title.casefold())
        if len(term) > 2 and term not in {"the", "and", "for", "that", "this", "with"}
    }


def title_similarity(left: str, right: str) -> float:
    left_terms = title_terms(left)
    right_terms = title_terms(right)
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / len(left_terms | right_terms)


def is_safe_fact_post(post: dict[str, Any], idol: str) -> bool:
    title = post["title"]
    lowered = title.casefold()
    words = re.findall(r"\b\w+\b", title)
    return bool(
        post["id"]
        and post["permalink"].startswith("/")
        and idol.casefold() in lowered
        and MIN_FACT_SCORE <= post["score"]
        and 5 <= len(words) <= MAX_POST_TITLE_WORDS
        and not post["over_18"]
        and not post["stickied"]
        and not post["removed"]
        and not title.rstrip().endswith("?")
        and not any(term in lowered for term in SPECULATION_TERMS)
    )


def fact_score(post: dict[str, Any]) -> float:
    title = post["title"]
    concrete_bonus = 3.0 if re.search(
        r"(?:\b\d+[,.]?\d*\b|\$|%|first|debut|year|years)", title, re.I
    ) else 0.0
    discussion = math.log10(post["score"] + 10) * 3 + math.log10(post["num_comments"] + 5)
    length_bonus = 2.0 if 8 <= len(title.split()) <= 20 else 0.0
    return discussion + concrete_bonus + length_bonus


def select_fact_posts(
    posts: Iterable[dict[str, Any]],
    idol: str,
    *,
    count: int,
    excluded_urls: Iterable[str] = (),
) -> list[dict[str, Any]]:
    if count not in {3, 4}:
        raise RedditSourceError("Idol Shorts must contain exactly 3 or 4 facts")
    excluded = set(excluded_urls)
    ranked = sorted(
        (post for post in posts if is_safe_fact_post(post, idol)),
        key=fact_score,
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    for post in ranked:
        source_url = reddit_post_url(post["permalink"])
        if source_url in excluded:
            continue
        if any(title_similarity(post["title"], item["title"]) >= 0.58 for item in selected):
            continue
        selected.append(post)
        if len(selected) == count:
            return selected
    raise RedditSourceError(
        f"Reddit returned only {len(selected)} safe, distinct {idol} fact posts; "
        f"need {count}. Try broader subreddits or a different idol."
    )


def is_safe_clip_post(post: dict[str, Any], idol: str) -> bool:
    return bool(
        post["video_url"]
        and idol.casefold() in post["title"].casefold()
        and post["score"] >= MIN_CLIP_SCORE
        and 2 <= post["video_duration"] <= 180
        and not post["over_18"]
        and not post["stickied"]
        and not post["removed"]
        and not any(term in post["title"].casefold() for term in SPECULATION_TERMS)
    )


def rank_clip_posts(
    posts: Iterable[dict[str, Any]],
    idol: str,
    *,
    excluded_urls: Iterable[str] = (),
) -> list[dict[str, Any]]:
    excluded = set(excluded_urls)
    ranked = sorted(
        (post for post in posts if is_safe_clip_post(post, idol)),
        key=lambda post: (post["score"], post["num_comments"]),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    seen_videos: set[str] = set()
    for post in ranked:
        source_url = reddit_post_url(post["permalink"])
        if source_url in excluded or post["video_url"] in seen_videos:
            continue
        selected.append(post)
        seen_videos.add(post["video_url"])
    return selected


def select_clip_posts(
    posts: Iterable[dict[str, Any]],
    idol: str,
    *,
    count: int,
    excluded_urls: Iterable[str] = (),
) -> list[dict[str, Any]]:
    selected = rank_clip_posts(posts, idol, excluded_urls=excluded_urls)
    if len(selected) >= count:
        return selected[:count]
    raise RedditSourceError(
        f"Reddit returned only {len(selected)} safe hosted {idol} clips; need {count}. "
        "Try broader subreddits or a different idol."
    )


class OldRedditSearchParser(HTMLParser):
    """Extract public search cards without executing page scripts."""

    def __init__(self, subreddit: str) -> None:
        super().__init__(convert_charrefs=True)
        self.subreddit = subreddit
        self.posts: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.depth = 0
        self.capture = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        classes = set(values.get("class", "").split())
        if tag == "div" and "thing" in classes and values.get("data-fullname", "").startswith("t3_"):
            self.current = {
                "id": values["data-fullname"].removeprefix("t3_"),
                "title": "",
                "author": "unknown",
                "subreddit": self.subreddit,
                "score": int(values.get("data-score") or 0),
                "num_comments": 0,
                "created_utc": 0,
                "permalink": values.get("data-permalink", ""),
                "over_18": "over18" in classes,
                "stickied": "stickied" in classes,
                "selftext": "",
                "url": values.get("data-url", ""),
            }
            self.depth = 1
            return
        if self.current and tag == "div":
            self.depth += 1
        if self.current and tag == "a":
            if "title" in classes:
                self.capture = "title"
            elif "author" in classes:
                self.capture = "author"
            elif "comments" in classes:
                self.capture = "comments"

    def handle_endtag(self, tag: str) -> None:
        if self.current and tag == "a":
            self.capture = ""
        if self.current and tag == "div":
            self.depth -= 1
            if self.depth == 0:
                self.posts.append(normalize_post(self.current))
                self.current = None

    def handle_data(self, data: str) -> None:
        if not self.current or not self.capture:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self.capture == "title":
            self.current["title"] = (self.current["title"] + " " + text).strip()
        elif self.capture == "author":
            self.current["author"] = text
        elif self.capture == "comments":
            match = re.search(r"\d[\d,]*", text)
            if match:
                self.current["num_comments"] = int(match.group().replace(",", ""))


def parse_old_reddit_html(content: str, subreddit: str) -> list[dict[str, Any]]:
    parser = OldRedditSearchParser(subreddit)
    parser.feed(content)
    return parser.posts


def parse_reddit_rss(content: str, subreddit: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise RedditSourceError(f"Reddit RSS was invalid: {exc}") from exc
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    posts: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", namespace):
        title = entry.findtext("atom:title", default="", namespaces=namespace)
        identity = entry.findtext("atom:id", default="", namespaces=namespace)
        post_id = identity.rsplit("_", 1)[-1] if identity else ""
        link_node = entry.find("atom:link", namespace)
        link = link_node.attrib.get("href", "") if link_node is not None else ""
        parsed = urlparse(link)
        permalink = parsed.path if parsed.hostname and "reddit.com" in parsed.hostname else ""
        content_text = entry.findtext("atom:content", default="", namespaces=namespace)
        video_match = re.search(r"https://v\.redd\.it/[A-Za-z0-9]+(?:/[^\s\"'<>]+)?", html.unescape(content_text))
        posts.append(
            normalize_post(
                {
                    "id": post_id,
                    "title": title,
                    "author": "unknown",
                    "subreddit": subreddit,
                    "score": MIN_FACT_SCORE,
                    "num_comments": 0,
                    "permalink": permalink,
                    "url": video_match.group(0) if video_match else "",
                }
            )
        )
    return posts


class RedditClient:
    """Credential-free fetcher with official and public-archive fallbacks."""

    def __init__(
        self,
        *,
        user_agent: str,
        session: requests.Session | None = None,
    ) -> None:
        if not user_agent or len(user_agent) < 8:
            raise RedditSourceError("REDDIT_USER_AGENT must identify this automation")
        self.user_agent = user_agent
        self.session = session or web_session(user_agent)

    def _get_json_posts(self, url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        response = self.session.get(
            url,
            params=params,
            headers={"Accept": "application/json"},
            timeout=(10, 45),
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        payload = response.json()
        children = payload.get("data", {}).get("children", [])
        return [
            normalize_post(child["data"])
            for child in children
            if isinstance(child, dict) and isinstance(child.get("data"), dict)
        ]

    def search(
        self,
        subreddit: str,
        query: str,
        *,
        limit: int = 100,
        require_video: bool = False,
    ) -> list[dict[str, Any]]:
        name = parse_subreddits([subreddit])[0]
        limit = min(100, max(10, limit))
        errors: list[str] = []
        search_query = f"{query} url:v.redd.it" if require_video else query
        common_params = {
            "q": search_query,
            "restrict_sr": "on",
            "sort": "top",
            "t": "year",
            "limit": limit,
            "raw_json": 1,
        }
        for root in PUBLIC_JSON_ROOTS:
            try:
                posts = self._get_json_posts(f"{root}/r/{name}/search.json", common_params)
                if posts and (not require_video or any(post["video_url"] for post in posts)):
                    return posts
            except (requests.RequestException, ValueError, AttributeError) as exc:
                errors.append(f"{urlparse(root).hostname} JSON: {exc}")

        try:
            response = self.session.get(
                f"https://www.reddit.com/r/{name}/search.rss",
                params={key: value for key, value in common_params.items() if key not in {"raw_json", "limit"}},
                headers={"Accept": "application/atom+xml, application/xml;q=0.9"},
                timeout=(10, 45),
            )
            response.raise_for_status()
            posts = parse_reddit_rss(response.text, name)
            if posts and (not require_video or any(post["video_url"] for post in posts)):
                return posts
        except (requests.RequestException, RedditSourceError) as exc:
            errors.append(f"Reddit RSS: {exc}")

        try:
            response = self.session.get(
                f"https://old.reddit.com/r/{name}/search",
                params={key: value for key, value in common_params.items() if key != "raw_json"},
                headers={"Accept": "text/html,application/xhtml+xml"},
                timeout=(10, 45),
            )
            response.raise_for_status()
            posts = parse_old_reddit_html(response.text, name)
            if posts and (not require_video or any(post["video_url"] for post in posts)):
                return posts
        except requests.RequestException as exc:
            errors.append(f"Old Reddit HTML: {exc}")

        try:
            archive_posts: list[dict[str, Any]] = []
            before: int | None = None
            page_count = 5 if require_video else 1
            for _page in range(page_count):
                params: dict[str, Any] = {
                    "subreddit": name,
                    "after": int(time.time() - 370 * 86_400),
                    "limit": min(100, limit),
                    "sort": "desc",
                }
                if require_video:
                    if before is not None:
                        params["before"] = before
                else:
                    params["title"] = query
                response = self.session.get(
                    ARCTIC_SHIFT_SEARCH_URL,
                    params=params,
                    headers={"Accept": "application/json"},
                    timeout=(10, 60),
                )
                response.raise_for_status()
                response.encoding = "utf-8"
                payload = response.json()
                items = payload.get("data") or []
                if not items:
                    break
                page_posts = [
                    normalize_post(item) for item in items if isinstance(item, dict)
                ]
                if require_video:
                    page_posts = [
                        post
                        for post in page_posts
                        if query.casefold() in post["title"].casefold() and post["video_url"]
                    ]
                archive_posts.extend(page_posts)
                if not require_video or len(archive_posts) >= 12:
                    break
                timestamps = [
                    int(float(item.get("created_utc") or 0))
                    for item in items
                    if isinstance(item, dict) and item.get("created_utc")
                ]
                if not timestamps:
                    break
                before = min(timestamps) - 1
            if archive_posts and (
                not require_video or any(post["video_url"] for post in archive_posts)
            ):
                return archive_posts
        except (requests.RequestException, ValueError, AttributeError) as exc:
            errors.append(f"Arctic Shift archive: {exc}")

        try:
            response = self.session.get(
                PULLPUSH_SEARCH_URL,
                params={
                    "q": query,
                    "subreddit": name,
                    "size": limit,
                    "sort": "desc",
                    "sort_type": "score",
                },
                headers={"Accept": "application/json"},
                timeout=(10, 45),
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            payload = response.json()
            posts = [normalize_post(item) for item in payload.get("data", []) if isinstance(item, dict)]
            if posts and (not require_video or any(post["video_url"] for post in posts)):
                return posts
        except (requests.RequestException, ValueError, AttributeError) as exc:
            errors.append(f"public archive: {exc}")

        raise RedditSourceError(f"Credential-free Reddit fetch failed for r/{name}: {'; '.join(errors)}")

    def discover(self, idol: str, subreddits: Iterable[str]) -> list[dict[str, Any]]:
        posts: list[dict[str, Any]] = []
        errors: list[str] = []
        seen: set[str] = set()
        configured = parse_subreddits(subreddits)
        specific = IDOL_SUBREDDITS.get(idol.casefold(), ())
        search_subreddits = parse_subreddits([*configured, *specific])
        for subreddit in search_subreddits:
            results: list[dict[str, Any]] = []
            try:
                results.extend(self.search(subreddit, idol))
            except RedditSourceError as exc:
                errors.append(str(exc))
            try:
                video_results = self.search(
                    subreddit,
                    idol,
                    require_video=True,
                )
                results.extend(video_results)
            except RedditSourceError as exc:
                errors.append(str(exc))
            for post in results:
                if post["id"] and post["id"] not in seen:
                    posts.append(post)
                    seen.add(post["id"])
        if not posts:
            detail = "; ".join(errors) if errors else "no matching posts"
            raise RedditSourceError(f"No public Reddit results found for {idol}: {detail}")
        return posts
