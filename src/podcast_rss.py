from __future__ import annotations

import html
import random
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .config_loader import Settings
from .utils import run


USER_AGENT = "horror-video-automation/2.0 (podcast RSS fallback)"


@dataclass(frozen=True)
class PodcastEpisode:
    episode_id: str
    title: str
    podcast: str
    audio_url: str
    webpage_url: str
    duration: float
    description: str
    transcript_url: str


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _duration_seconds(value: str) -> float:
    value = value.strip()
    if not value:
        return 0.0
    try:
        if ":" not in value:
            return float(value)
        pieces = [float(piece) for piece in value.split(":")]
        total = 0.0
        for piece in pieces:
            total = total * 60.0 + piece
        return total
    except ValueError:
        return 0.0


def _text(item: ET.Element, name: str) -> str:
    node = next((child for child in item.iter() if _local_name(child.tag) == name), None)
    return str(node.text or "").strip() if node is not None else ""


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value))).strip()


def _episodes_from_feed(feed_url: str, podcast_name: str, settings: Settings,
                        history_ids: set[str]) -> list[PodcastEpisode]:
    response = requests.get(feed_url, timeout=15, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    episodes: list[PodcastEpisode] = []
    for item in (node for node in root.iter() if _local_name(node.tag) == "item"):
        enclosure = next((child for child in item if _local_name(child.tag) == "enclosure"
                          and child.attrib.get("url")), None)
        if enclosure is None:
            continue
        audio_url = str(enclosure.attrib["url"])
        guid = _text(item, "guid") or audio_url
        episode_id = "rss-" + __import__("hashlib").sha256(guid.encode("utf-8")).hexdigest()[:16]
        if episode_id in history_ids:
            continue
        duration = _duration_seconds(_text(item, "duration"))
        if duration and not settings.min_source_duration <= duration <= settings.max_source_duration:
            continue
        transcript = next((child for child in item.iter()
                           if _local_name(child.tag) == "transcript"
                           and "vtt" in str(child.attrib.get("type", "")).casefold()
                           and child.attrib.get("url")), None)
        episodes.append(PodcastEpisode(
            episode_id=episode_id,
            title=_text(item, "title") or "Untitled horror podcast episode",
            podcast=podcast_name,
            audio_url=audio_url,
            webpage_url=_text(item, "link") or feed_url,
            duration=duration,
            description=_plain_text(_text(item, "description") or _text(item, "summary")),
            transcript_url=str(transcript.attrib["url"]) if transcript is not None else "",
        ))
    return episodes


def search_podcast_episodes(keyword: str, settings: Settings, history_ids: set[str],
                            limit: int = 6) -> list[PodcastEpisode]:
    """Search public podcast feeds without requiring a platform login or API key."""
    response = requests.get(
        "https://itunes.apple.com/search",
        params={"term": keyword, "media": "podcast", "entity": "podcast", "country": "US", "limit": 12},
        timeout=15, headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    feeds = [(str(item.get("feedUrl") or ""), str(item.get("collectionName") or "Horror podcast"))
             for item in response.json().get("results", []) if item.get("feedUrl")]
    random.shuffle(feeds)
    episodes: list[PodcastEpisode] = []
    for feed_url, name in feeds[:8]:
        try:
            candidates = _episodes_from_feed(feed_url, name, settings, history_ids)
        except (requests.RequestException, ET.ParseError, ValueError):
            continue
        random.shuffle(candidates)
        episodes.extend(candidates[:2])
        if len(episodes) >= limit:
            break
    random.shuffle(episodes)
    return episodes[:limit]


def download_episode_audio(episode: PodcastEpisode, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(episode.audio_url, stream=True, timeout=(15, 60),
                      headers={"User-Agent": USER_AGENT}) as response:
        response.raise_for_status()
        with destination.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    output.write(chunk)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("podcast RSS audio download was empty")
    return destination


def download_episode_transcript(episode: PodcastEpisode, destination: Path) -> Path | None:
    if not episode.transcript_url:
        return None
    response = requests.get(episode.transcript_url, timeout=20, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    if "WEBVTT" not in response.text[:100].upper():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(response.text, encoding="utf-8")
    return destination


def make_audio_visual_source(audio: Path, destination: Path, start: float, end: float) -> Path:
    """Make a cheap dark base track; stock footage is overlaid by the final compositor."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    length = max(1.0, end - start)
    command = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x07080d:s=540x960:r=2",
        "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(audio),
        "-map", "0:v", "-map", "1:a", "-t", f"{length:.3f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", str(destination),
    ]
    result = run(command, check=False, timeout=600)
    if result.returncode or not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"podcast audio visual source failed: {result.stderr[-1200:]}")
    return destination
