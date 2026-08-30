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

USER_AGENT = "horror-shorts-automation/3.0 (github.com/Skip-me-not/horror-video-automation)"
ATOM = "{http://www.w3.org/2005/Atom}"
HORROR_TERMS = {
    "apparition", "attic", "basement", "blood", "cemetery", "creature", "dark",
    "dead", "death", "demon", "disappeared", "door", "figure", "footsteps",
    "ghost", "haunted", "hallway", "heard", "hospital", "knocking", "murder",
    "night", "paranormal", "possessed", "saw", "scream", "shadow", "stranger",
    "unexplained", "voice", "window",
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


def _fetch(url: str) -> bytes:
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.2",
    })
    with urlopen(request, timeout=30) as response:
        return response.read()


def parse_comment_feed(payload: bytes, post_id: str) -> tuple[str, ...]:
    root = ET.fromstring(payload)
    values: list[str] = []
    for entry in root.findall(f"{ATOM}entry"):
        if (entry.findtext(f"{ATOM}id") or "") in {f"t3_{post_id}", post_id}:
            continue
        text = _plain_text(entry.findtext(f"{ATOM}content") or "")
        if 5 <= len(text.split()) <= 70 and text not in values:
            values.append(text)
    return tuple(values[:8])


def _score(post: RedditVideoPost) -> float:
    searchable = f"{post.title} {post.body}".casefold()
    return sum(2.0 for term in HORROR_TERMS if term in searchable) + min(6.0, len(post.body) / 80.0)


def discover_video_posts(root: Path, used_ids: set[str], seed: str = "") -> list[RedditVideoPost]:
    config: dict[str, Any] = read_json(root / "config" / "reddit_sources.json")
    subreddits = [str(value) for value in config["subreddits"]]
    random.Random(seed).shuffle(subreddits)
    errors: list[str] = []
    candidates: list[RedditVideoPost] = []
    for subreddit in subreddits[: int(config.get("maximum_feed_attempts", 3))]:
        try:
            url = (f"https://www.reddit.com/r/{quote(subreddit)}/{quote(str(config.get('listing', 'top')))}/"
                   f".rss?t={quote(str(config.get('period', 'month')))}")
            candidates.extend(post for post in parse_video_feed(_fetch(url), subreddit)
                              if post.post_id not in used_ids)
            if len(candidates) >= 4:
                break
        except (HTTPError, URLError, TimeoutError, ET.ParseError, OSError) as exc:
            errors.append(f"r/{subreddit}: {exc}")
            time.sleep(1)
    if not candidates:
        raise RuntimeError("no unused Reddit-hosted horror video was available: " + " | ".join(errors))
    candidates.sort(key=lambda item: (_score(item), item.published), reverse=True)
    shortlist = candidates[: min(12, len(candidates))]
    random.Random(seed + ":order").shuffle(shortlist)
    return shortlist


def enrich_with_comments(post: RedditVideoPost) -> RedditVideoPost:
    try:
        time.sleep(1.2)
        comments = parse_comment_feed(_fetch(post.post_url.rstrip("/") + "/.rss"), post.post_id)
        return replace(post, comments=comments)
    except (HTTPError, URLError, TimeoutError, ET.ParseError, OSError):
        return post


def select_video_post(root: Path, used_ids: set[str], seed: str = "") -> RedditVideoPost:
    return enrich_with_comments(discover_video_posts(root, used_ids, seed)[0])


def _excerpt(value: str, maximum_words: int) -> str:
    value = value.replace("WTF", "what the hell").replace("wtf", "what the hell")
    value = re.sub(r"[*_`#>]", "", value)
    return " ".join(re.sub(r"\s+", " ", value).strip().split()[:maximum_words]).rstrip(" ,;:")


def build_narration(post: RedditVideoPost, target_words: int = 135) -> dict[str, Any]:
    title, body = _excerpt(post.title, 20), _excerpt(post.body, 55)
    author = post.author.removeprefix("/u/")
    parts = [f"This video was posted to r {post.subreddit} by a user named {author}.",
             f"The title was: {title}."]
    if body and body.casefold() not in title.casefold():
        parts.append(f"The uploader added one detail: {body}.")
    parts.append("Watch the center of the original clip closely. The disturbing part is easy to miss on the first viewing.")
    if post.comments:
        parts.extend(["The comment section immediately split into two explanations.",
                      f"One viewer pointed out: {_excerpt(post.comments[0], 22)}."])
        if len(post.comments) > 1:
            parts.append(f"Another viewer disagreed, saying: {_excerpt(post.comments[1], 22)}.")
    else:
        parts.extend(["Some viewers would call it a shadow, compression, or a person hidden by the camera angle.",
                      "Others believe the movement does not match anything visible in the scene."])
    parts.append("The post included no independent source that could confirm what the camera captured, so the clip remains unexplained.")
    narration = " ".join(" ".join(parts).split()[:target_words]).rstrip(" ,;:") + "."
    core = _excerpt(title, 7).upper()
    hook = f"WATCH CLOSELY — {core}" if core else "WATCH THE CENTER OF THIS REDDIT VIDEO"
    if len(hook) > 58:
        hook = f"WATCH CLOSELY — {_excerpt(title, 5).upper()}"
    important = [term for term in HORROR_TERMS if term in narration.casefold()]
    important.extend(["WATCH", "ORIGINAL", "UNEXPLAINED"])
    return {"narration": narration, "hook": hook,
            "important_terms": list(dict.fromkeys(important))[:16],
            "word_count": len(narration.split())}
