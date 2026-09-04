from __future__ import annotations

import html
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config_loader import read_json
from .utils import write_json

USER_AGENT = "lululala-celebrity-shorts/1.0 (github.com/Skip-me-not/horror-video-automation)"
ATOM = "{http://www.w3.org/2005/Atom}"

KPOP_NAMES = (
    "LE SSERAFIM", "Stray Kids", "BABYMONSTER", "NewJeans", "SEVENTEEN",
    "BLACKPINK", "KATSEYE", "ENHYPEN", "G-IDLE", "(G)I-DLE", "ATEEZ",
    "TWICE", "aespa", "ILLIT", "RIIZE", "NCT", "EXO", "TXT", "IVE", "BTS",
    "Jungkook", "J-Hope", "Jennie", "Rosé", "Jisoo", "Lisa", "Jimin", "Suga",
    "Karina", "Winter", "Wonyoung", "Yujin", "Chaewon", "Sakura", "Felix", "Hyunjin", "Jin", "RM",
)
GLOBAL_NAMES = (
    "Millie Bobby Brown", "Anya Taylor-Joy", "Timothée Chalamet", "Sabrina Carpenter",
    "Olivia Rodrigo", "Sydney Sweeney", "Florence Pugh", "Jenna Ortega", "Sadie Sink",
    "Pedro Pascal", "Jacob Elordi", "Ariana Grande", "Taylor Swift", "Billie Eilish",
    "Selena Gomez", "Chappell Roan", "The Weeknd", "Harry Styles", "Dua Lipa",
    "Tate McRae", "Lady Gaga", "Zendaya",
)
KPOP_SUBREDDITS = {
    "kpop", "kpopthoughts", "kpop_uncensored", "blackpink", "bangtan", "twice",
    "aespa", "ive", "lesserafim", "straykids", "seventeen", "nct", "exo",
    "babymonster", "illit", "gidle", "ateez", "riize", "katseye",
}
TREND_TERMS = {
    "viral", "trending", "performance", "interview", "award", "fashion", "reaction",
    "moment", "stage", "concert", "dance", "comeback", "teaser", "premiere", "fans",
}
BLOCKED_COMMENT_TERMS = {
    "automoderator", "i am a bot", "kill yourself", "ugly", "fat", "skinny",
    "slut", "whore", "bitch", "drug addict", "looks drunk", "mental illness",
}


@dataclass(frozen=True)
class RedditVideoPost:
    post_id: str
    subreddit: str
    title: str
    body: str
    author: str
    post_url: str
    video_url: str
    published: str
    comments: tuple[str, ...] = ()


def _decoded_html(value: str) -> str:
    return html.unescape(html.unescape(value or ""))


def _plain_text(value: str) -> str:
    value = _decoded_html(value)
    match = re.search(
        r"<!--\s*SC_OFF\s*-->\s*<div[^>]*class=[\"']md[\"'][^>]*>(.*?)</div>\s*<!--\s*SC_ON\s*-->",
        value, flags=re.I | re.S,
    )
    if match:
        value = match.group(1)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</p\s*>", "\n\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"(?im)^\s*(edit|update|tl;?dr)\s*:.*$", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n\s*\n+", "\n\n", value)
    return value.strip()


def parse_video_feed(payload: bytes, subreddit: str) -> list[RedditVideoPost]:
    root = ET.fromstring(payload)
    posts: list[RedditVideoPost] = []
    for entry in root.findall(f"{ATOM}entry"):
        raw_content = entry.findtext(f"{ATOM}content") or ""
        decoded = _decoded_html(raw_content)
        video_match = re.search(r'href=[\"\'](https://v\.redd\.it/[A-Za-z0-9]+)[\"\']', decoded, re.I)
        if not video_match:
            continue
        author_node = entry.find(f"{ATOM}author")
        author = _plain_text(author_node.findtext(f"{ATOM}name") or "unknown") if author_node is not None else "unknown"
        link_node = entry.find(f"{ATOM}link")
        post_url = str(link_node.attrib.get("href") or "") if link_node is not None else ""
        raw_id = entry.findtext(f"{ATOM}id") or post_url
        post_id = raw_id.removeprefix("t3_").rstrip("/").rsplit("/", 1)[-1]
        posts.append(RedditVideoPost(
            post_id, subreddit, _plain_text(entry.findtext(f"{ATOM}title") or ""),
            _plain_text(raw_content), author, post_url, video_match.group(1),
            entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated") or "",
        ))
    return posts


def _fetch(url: str, attempts: int = 4) -> bytes:
    """Fetch a Reddit feed with bounded backoff for shared GitHub runner rate limits."""
    last_error: Exception | None = None
    retryable_statuses = {429, 500, 502, 503, 504}
    for attempt in range(max(1, attempts)):
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.2"})
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            last_error = exc
            if exc.code not in retryable_statuses or attempt >= attempts - 1:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else 8.0 * (2 ** attempt)
            except ValueError:
                delay = 8.0 * (2 ** attempt)
            time.sleep(min(90.0, max(2.0, delay)))
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt >= attempts - 1:
                raise
            time.sleep(min(45.0, 5.0 * (2 ** attempt)))
    raise RuntimeError(f"request failed without a response: {last_error}")


def parse_comment_feed(payload: bytes, post_id: str) -> tuple[str, ...]:
    root = ET.fromstring(payload)
    values: list[str] = []
    for entry in root.findall(f"{ATOM}entry"):
        if (entry.findtext(f"{ATOM}id") or "") in {f"t3_{post_id}", post_id}:
            continue
        text = _plain_text(entry.findtext(f"{ATOM}content") or "")
        lowered = text.casefold()
        if (5 <= len(text.split()) <= 70 and text not in values
                and not any(term in lowered for term in BLOCKED_COMMENT_TERMS)):
            values.append(text)
    return tuple(values[:8])


def _name_match(text: str, names: tuple[str, ...]) -> str:
    for name in sorted(names, key=len, reverse=True):
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text, re.I):
            return name
    return ""


def _excerpt(value: str, maximum_words: int) -> str:
    value = value.replace("WTF", "what the heck").replace("wtf", "what the heck")
    value = re.sub(r"[*_`#>]", "", value)
    return " ".join(re.sub(r"\s+", " ", value).strip().split()[:maximum_words]).rstrip(" ,;:")


def featured_subject(post: RedditVideoPost) -> tuple[str, bool]:
    searchable = f"{post.title} {post.body}"
    kpop = _name_match(searchable, KPOP_NAMES)
    if kpop:
        return kpop, True
    global_name = _name_match(searchable, GLOBAL_NAMES)
    if global_name:
        return global_name, False
    fallback = _excerpt(post.title, 4).strip(" -:|[]()")
    if post.subreddit.casefold() in KPOP_SUBREDDITS:
        return fallback or "this K-pop artist", True
    return fallback or "this celebrity", False


def _score(post: RedditVideoPost) -> float:
    searchable = f"{post.title} {post.body}".casefold()
    subject, is_kpop = featured_subject(post)
    named = subject.casefold() in searchable and not subject.startswith("this ")
    return ((16.0 if is_kpop else 0.0) + (12.0 if named else 0.0)
            + sum(2.0 for term in TREND_TERMS if term in searchable)
            + min(5.0, len(post.body) / 100.0))


def _pool_path(root: Path) -> Path:
    return root / "data" / "celebrity_source_pool.json"


def _load_pool(root: Path, used_ids: set[str]) -> list[RedditVideoPost]:
    path = _pool_path(root)
    if not path.is_file():
        return []
    try:
        payload = read_json(path)
    except (OSError, ValueError):
        return []
    posts: list[RedditVideoPost] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        post_id, post_url, video_url = str(item.get("post_id") or ""), str(item.get("post_url") or ""), str(item.get("video_url") or "")
        if (not post_id or post_id in used_ids or not post_url.startswith("https://www.reddit.com/") or not video_url.startswith("https://v.redd.it/")):
            continue
        posts.append(RedditVideoPost(
            post_id=post_id, subreddit=str(item.get("subreddit") or "popculturechat"),
            title=str(item.get("title") or "Celebrity moment shared on Reddit"), body=str(item.get("body") or ""),
            author=str(item.get("author") or "unknown"), post_url=post_url, video_url=video_url,
            published=str(item.get("published") or ""), comments=tuple(str(value) for value in item.get("comments", [])[:2]),
        ))
    return posts


def _save_pool(root: Path, posts: list[RedditVideoPost], used_ids: set[str], limit: int) -> None:
    unique = {post.post_id: post for post in posts if post.post_id not in used_ids}
    ordered = sorted(unique.values(), key=lambda item: (_score(item), item.published), reverse=True)[:limit]
    write_json(_pool_path(root), [{"post_id": post.post_id, "subreddit": post.subreddit, "title": post.title,
        "body": post.body, "author": post.author, "post_url": post.post_url, "video_url": post.video_url,
        "published": post.published, "comments": list(post.comments[:2])} for post in ordered])


def discover_video_posts(root: Path, used_ids: set[str], seed: str = "") -> list[RedditVideoPost]:
    config: dict[str, Any] = read_json(root / "config" / "reddit_sources.json")
    subreddits = [str(value) for value in config["subreddits"]]
    random.Random(seed).shuffle(subreddits)
    errors: list[str] = []
    cached = _load_pool(root, used_ids)
    candidates = list(cached)
    if len(cached) < int(config.get("refresh_pool_below", 12)):
        hosts = [str(value) for value in config.get("feed_hosts", ["www.reddit.com", "old.reddit.com"])]
        target_size, request_attempts = int(config.get("target_pool_size", 24)), int(config.get("request_attempts", 3))
        for subreddit in subreddits[: int(config.get("maximum_feed_attempts", len(subreddits)))]:
            fetched = False
            for host in hosts:
                try:
                    listing = quote(str(config.get("listing", "top")))
                    url = f"https://{host}/r/{quote(subreddit)}/{listing}.rss?t={quote(str(config.get('period', 'week')))}"
                    candidates.extend(post for post in parse_video_feed(_fetch(url, attempts=request_attempts), subreddit) if post.post_id not in used_ids)
                    fetched = True
                    break
                except (HTTPError, URLError, TimeoutError, ET.ParseError, OSError) as exc:
                    errors.append(f"r/{subreddit} via {host}: {exc}")
            if fetched and len({post.post_id for post in candidates}) >= target_size:
                break
        if len(candidates) > len(cached):
            _save_pool(root, candidates, used_ids, int(config.get("pool_limit", 160)))
    if not candidates:
        raise RuntimeError("no unused Reddit-hosted celebrity video was available: " + " | ".join(errors))
    unique = list({post.post_id: post for post in candidates}.values())
    kpop = sorted((post for post in unique if featured_subject(post)[1]), key=lambda item: (_score(item), item.published), reverse=True)
    global_celeb = sorted((post for post in unique if not featured_subject(post)[1]), key=lambda item: (_score(item), item.published), reverse=True)
    prefer_kpop = random.Random(seed + ":category").random() < float(config.get("kpop_selection_weight", 0.75))
    primary, secondary = (kpop, global_celeb) if prefer_kpop else (global_celeb, kpop)
    primary, secondary = primary[:12], secondary[:12]
    random.Random(seed + ":primary").shuffle(primary)
    random.Random(seed + ":secondary").shuffle(secondary)
    return primary + secondary


def enrich_with_comments(post: RedditVideoPost) -> RedditVideoPost:
    try:
        time.sleep(1.2)
        comments = parse_comment_feed(_fetch(post.post_url.rstrip("/") + "/.rss", attempts=1), post.post_id)
        return replace(post, comments=comments)
    except (HTTPError, URLError, TimeoutError, ET.ParseError, OSError):
        return post


def select_video_post(root: Path, used_ids: set[str], seed: str = "") -> RedditVideoPost:
    return enrich_with_comments(discover_video_posts(root, used_ids, seed)[0])


def build_narration(post: RedditVideoPost, target_words: int = 135) -> dict[str, Any]:
    title, body = _excerpt(post.title, 24), _excerpt(post.body, 48)
    subject, is_kpop = featured_subject(post)
    author = post.author.removeprefix("/u/")
    parts = [f"A video featuring {subject} is getting attention on Reddit.",
             f"It was shared in r {post.subreddit} by {author}, with the title: {title}."]
    if body and body.casefold() not in title.casefold():
        parts.append(f"The person who posted it added this context: {body}.")
    parts.append("The opening clip is the moment people keep replaying, so watch the expression and timing closely.")
    if post.comments:
        parts.extend(["The Reddit comments show why the clip caught on.",
                      f"One fan's reaction was: {_excerpt(post.comments[0], 23)}."])
        if len(post.comments) > 1:
            parts.append(f"Another viewer added: {_excerpt(post.comments[1], 23)}.")
    else:
        parts.extend([
            "Viewers focused on the performance, expression, and tiny details that are easy to miss at full speed.",
            "The replay makes the timing clearer and shows why a short, unscripted-looking moment can travel quickly between fan communities.",
            "Rather than changing the clip's meaning, this edit keeps the original sequence visible while explaining the context Reddit supplied.",
        ])
    parts.append("This recap describes the Reddit post and fan reactions; it does not independently confirm rumors or private claims.")
    parts.extend([
        "Its replay value comes from the timing, reaction, and small details already visible in the original video.",
        "That is why the moment can be interesting without treating the Reddit caption as confirmed reporting.",
    ])
    narration = " ".join(" ".join(parts).split()[:target_words]).rstrip(" ,;:.!?") + "."
    hook = f"{subject.upper()} MOMENT FANS KEEP REPLAYING" if is_kpop else f"WHY EVERYONE IS TALKING ABOUT {subject.upper()}"
    if len(hook) > 58:
        hook = f"THIS {subject.upper()} MOMENT WENT VIRAL"
    if len(hook) > 58:
        hook = "THE CELEBRITY MOMENT EVERYONE REPLAYED"
    subject_terms = [word for word in re.findall(r"[A-Za-z0-9]+", subject) if len(word) > 2]
    important = subject_terms + ["FANS", "MOMENT", "REPLAYING", "REDDIT", "VIRAL", "REACTION"]
    return {"narration": narration, "hook": hook, "important_terms": list(dict.fromkeys(important))[:16],
            "word_count": len(narration.split()), "subject": subject, "is_kpop": is_kpop,
            "title": f"{subject}: The Moment Fans Keep Replaying"}
