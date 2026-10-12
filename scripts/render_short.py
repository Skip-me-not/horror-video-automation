#!/usr/bin/env python3
"""Create a high-retention motivational micro-story Short."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import wave
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scripts.story_engine import (
    MAX_SECONDS,
    MIN_SECONDS,
    StoryError,
    estimate_beat_durations,
    load_stories,
    seconds_to_ass,
    select_hook,
    select_story,
    select_title,
    story_beats,
    story_history_event,
    story_script,
)


ROOT = Path(__file__).resolve().parents[1]
QUOTES_PATH = ROOT / "data" / "quotes.json"
STORIES_PATH = ROOT / "data" / "stories.json"
STATE_PATH = ROOT / "data" / "state.json"
OUTPUT_DIR = ROOT / "output"
POPPINS_FONT_PATH = ROOT / "assets" / "fonts" / "Poppins-SemiBold.ttf"
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/videos/search"
OPENVERSE_AUDIO_URL = "https://api.openverse.org/v1/audio/"
TTS_VOICE = "en_US-joe-medium"
TTS_MODEL_DIR = ROOT / ".tts-models"
IMPACT_MIN_SECONDS = 8.0
IMPACT_MAX_SECONDS = 14.5
OPENVERSE_TOKEN_URL = "https://api.openverse.org/v1/auth_tokens/token/"
FALLBACK_SEARCH = "calm sunrise nature"
MUSIC_SEARCHES = (
    "epic motivational music",
    "uplifting cinematic music",
    "powerful inspiring music",
    "motivational trailer music",
    "epic orchestral music",
    "inspiring background music",
)
OPENVERSE_LICENSES = {"cc0", "pdm"}
VIDEO_SECONDS = int(MAX_SECONDS)
WIDTH = 1080
HEIGHT = 1920
FPS = 30
HASHTAGS = "#motivation #discipline #success #mindset #shorts"
TRANSITION_SECONDS = 0.08
MUSIC_MIX_VOLUME = 0.30
MUSIC_DUCK_THRESHOLD = 0.06
MUSIC_DUCK_RATIO = 2.5
CLIP_COUNT = 3  # Legacy single-quote helper compatibility.
HOOKS = {
    "discipline": ("DO IT ANYWAY.", "STOP NEGOTIATING.", "KEEP THE PROMISE.", "NO MORE EXCUSES."),
    "success": ("PLAY THE LONG GAME.", "THIS IS HOW YOU WIN.", "BUILD IT QUIETLY.", "KEEP GOING."),
    "healing": ("YOU ARE STILL HEALING.", "BE GENTLE TODAY.", "LET IT GO SLOWLY.", "YOU WILL FEEL LIGHT AGAIN."),
    "confidence": ("TRUST YOURSELF AGAIN.", "YOU ARE MORE READY.", "TAKE UP SPACE.", "BACK YOURSELF."),
    "growth": ("YOUR NEXT CHAPTER STARTS NOW.", "OUTGROW THE OLD YOU.", "CHOOSE YOUR FUTURE.", "CHANGE STARTS HERE."),
    "consistency": ("SMALL STEPS STILL COUNT.", "SHOW UP AGAIN.", "DON'T BREAK THE RHYTHM.", "REPEAT WHAT WORKS."),
}
SUPPORTED_CATEGORIES = {
    "discipline",
    "success",
    "healing",
    "confidence",
    "growth",
    "consistency",
}


class ShortsError(RuntimeError):
    """A user-actionable automation error."""


def http_session() -> requests.Session:
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "github-youtube-shorts/1.0"})
    return session


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ShortsError(f"Required JSON file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ShortsError(f"Invalid JSON in {path}: {exc}") from exc


def load_quotes(path: Path = QUOTES_PATH) -> list[dict[str, str]]:
    payload = load_json(path)
    if not isinstance(payload, list) or not payload:
        raise ShortsError("The quote catalog is empty; add new original scripts before running again")
    seen: set[str] = set()
    quotes: list[dict[str, str]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ShortsError(f"Quote entry {index} must be an object")
        required = {"id", "quote", "insight", "pexels_search", "category"}
        if set(item) != required:
            raise ShortsError(f"Quote entry {index} must contain exactly {sorted(required)}")
        normalized = {key: str(item[key]).strip() for key in required}
        if not all(normalized.values()):
            raise ShortsError(f"Quote entry {index} contains an empty value")
        if normalized["id"] in seen:
            raise ShortsError(f"Duplicate quote id: {normalized['id']}")
        if normalized["category"] not in SUPPORTED_CATEGORIES:
            raise ShortsError(f"Unsupported quote category: {normalized['category']}")
        seen.add(normalized["id"])
        quotes.append(normalized)
    return quotes


def default_state() -> dict[str, Any]:
    return {"version": 1, "cycle": 1, "used_ids": [], "history": []}


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return default_state()
    payload = load_json(path)
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ShortsError("data/state.json must be a version 1 state object")
    used_ids = payload.get("used_ids", [])
    history = payload.get("history", [])
    cycle = payload.get("cycle", 1)
    if not isinstance(cycle, int) or cycle < 1:
        raise ShortsError("state.cycle must be a positive integer")
    if not isinstance(used_ids, list) or not all(isinstance(value, str) for value in used_ids):
        raise ShortsError("state.used_ids must be a list of strings")
    if not isinstance(history, list) or not all(isinstance(value, dict) for value in history):
        raise ShortsError("state.history must be a list of objects")
    return {"version": 1, "cycle": cycle, "used_ids": used_ids, "history": history}


def select_quote(
    quotes: list[dict[str, str]],
    state: dict[str, Any],
    *,
    rng: random.Random | random.SystemRandom | None = None,
) -> dict[str, str]:
    """Choose an unused quote; reset only after the complete catalog is used."""
    if not quotes:
        raise ShortsError("The quote catalog is empty")
    chooser = rng or random.SystemRandom()
    known_ids = {entry["id"] for entry in quotes}
    used = {value for value in state.get("used_ids", []) if value in known_ids}
    candidates = [entry for entry in quotes if entry["id"] not in used]
    if not candidates:
        raise ShortsError("All remaining scripts are already marked as used; refill the catalog")
    selected = chooser.choice(candidates)
    state.setdefault("used_ids", []).append(selected["id"])
    state.setdefault("history", []).append(
        {
            "id": selected["id"],
            "used_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )
    state["history"] = state["history"][-200:]
    state["version"] = 1
    state.setdefault("cycle", 1)
    return selected


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def wrap_quote(text: str, *, width: int = 22, max_lines: int = 5) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        raise ShortsError("Quote text cannot be empty")
    lines = textwrap.wrap(
        cleaned,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if len(lines) > max_lines:
        raise ShortsError(
            f"Quote needs {len(lines)} lines and exceeds the {max_lines}-line safe area"
        )
    if any(len(line) > width + 8 for line in lines):
        raise ShortsError("Quote contains a word too long for the text safe area")
    return "\n".join(lines)


def validate_channel_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned:
        raise ShortsError("CHANNEL_NAME is required")
    if len(cleaned) > 40:
        raise ShortsError("CHANNEL_NAME must be 40 characters or fewer to stay in the safe area")
    return cleaned


def make_title(quote: str) -> str:
    suffix = " #shorts"
    cleaned = re.sub(r"\s+", " ", quote).strip().strip('"')
    limit = 100 - len(suffix)
    if len(cleaned) > limit:
        shortened = cleaned[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:!?")
        cleaned = (shortened or cleaned[: limit - 1]).rstrip() + "…"
    return cleaned + suffix


def make_hook(entry: dict[str, str]) -> str:
    """Return a short, stable hook so retries render the same creative."""
    choices = HOOKS[entry["category"]]
    seed = sum(ord(character) for character in entry["id"])
    return choices[seed % len(choices)]


def ass_escape(value: str) -> str:
    return (
        value.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def wrap_caption(text: str, *, width: int = 30, max_lines: int = 4) -> str:
    """Wrap one short narration beat inside the mobile caption safe area."""
    return wrap_quote(text, width=width, max_lines=max_lines)


def build_story_subtitles(
    beats: list[dict[str, str]],
    durations: list[float],
    channel_name: str,
) -> str:
    """Build one closely timed caption event per information beat."""
    if len(beats) != len(durations) or not beats:
        raise ShortsError("Caption beats and durations must be non-empty and have equal lengths")
    channel = ass_escape(channel_name)
    events: list[str] = []
    start = 0.0
    for index, (beat, duration) in enumerate(zip(beats, durations, strict=True)):
        end = start + duration
        phase = beat["phase"]
        style = {
            "hook": "Hook",
            "problem": "Story",
            "turn": "Turn",
            "payoff": "Payoff",
        }.get(phase, "Story")
        max_lines = 3 if phase == "hook" else 4
        caption = ass_escape(wrap_caption(beat["text"], width=30, max_lines=max_lines))
        animation = r"{\an8\pos(540,500)\fad(140,180)\fscx103\fscy103\t(0,220,\fscx100\fscy100)}"
        events.append(
            f"Dialogue: 2,{seconds_to_ass(start)},{seconds_to_ass(end)},{style},,0,0,0,,"
            f"{animation}{caption}"
        )
        start = end
    total = sum(durations)
    events.append(
        f"Dialogue: 3,0:00:00.00,{seconds_to_ass(total)},Channel,,0,0,0,,"
        fr"{{\an2\pos(540,1700)}}{channel}"
    )
    return fr"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,Poppins SemiBold,64,&H0000D7FF,&H0000D7FF,&HD0000000,&H50000000,-1,0,0,0,100,100,1,0,1,4,1,5,92,170,0,1
Style: Story,Poppins SemiBold,47,&H00FFFFFF,&H00FFFFFF,&HD0000000,&H50000000,-1,0,0,0,100,100,0,0,1,4,1,5,92,170,0,1
Style: Turn,Poppins SemiBold,49,&H0000D7FF,&H0000D7FF,&HD0000000,&H50000000,-1,0,0,0,100,100,0,0,1,4,1,5,92,170,0,1
Style: Payoff,Poppins SemiBold,51,&H00FFFFFF,&H00FFFFFF,&HD0000000,&H60000000,-1,0,0,0,100,100,0,0,1,4,1,5,92,170,0,1
Style: Channel,Poppins SemiBold,30,&H10FFFFFF,&H10FFFFFF,&H60000000,&H50000000,-1,0,0,0,100,100,1,0,1,3,1,2,60,60,125,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""


def chunk_impact_text(text: str, max_words: int = 10) -> list[str]:
    """Split a concise quote into natural, mobile-sized spoken phrases."""
    words = re.findall(r"\S+", re.sub(r"\s+", " ", text).strip())
    if not words:
        raise ShortsError("Impact quote is empty")
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        terminal = word.endswith((".", "!", "?"))
        soft_break = word.endswith((",", ";")) and len(current) >= 5
        if len(current) >= max_words or terminal or soft_break:
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    if len(chunks) > 4:
        balanced_width = max(1, (len(words) + 3) // 4)
        chunks = [
            " ".join(words[index:index + balanced_width])
            for index in range(0, len(words), balanced_width)
        ]
    if len(chunks) >= 2 and len(chunks[-1].split()) <= 2:
        previous = chunks[-2].split()
        orphan = chunks[-1].split()
        move_count = min(3, max(0, len(previous) - 4))
        if move_count:
            chunks[-2] = " ".join(previous[:-move_count])
            chunks[-1] = " ".join(previous[-move_count:] + orphan)
    normalized: list[str] = []
    capitalize_next = True
    for chunk in chunks:
        if capitalize_next:
            chunk = chunk[:1].upper() + chunk[1:]
        normalized.append(chunk)
        capitalize_next = chunk.endswith((".", "!", "?"))
    return normalized


def impact_beats(story: dict[str, Any], hook: str) -> list[dict[str, str]]:
    """Condense a full catalog story into an original 2–4 phrase impact quote."""
    if story.get("quote_text"):
        text = story["quote_text"]
        visual = story["hook_visual"]
    elif story["id"] == "manual":
        text = hook
        visual = story["hook_visual"]
    else:
        turns = [beat for beat in story["beats"] if beat["phase"] == "turn"]
        payoff = next(beat for beat in reversed(story["beats"]) if beat["phase"] == "payoff")
        chosen_turn = turns[0] if turns else story["beats"][-2]
        text = f"{chosen_turn['text']} {payoff['text']}"
        visual = chosen_turn["visual_search"] or story["hook_visual"]
    phrases = chunk_impact_text(text)
    phases = ["payoff"] if len(phrases) == 1 else (
        ["hook"] + ["turn"] * max(0, len(phrases) - 2) + ["payoff"]
    )
    return [
        {"phase": phase, "text": phrase, "visual_search": visual}
        for phase, phrase in zip(phases, phrases, strict=True)
    ]


def build_impact_subtitles(
    beats: list[dict[str, str]], durations: list[float], channel_name: str
) -> str:
    """Minimal reference-inspired captions: one short white phrase at a time."""
    if len(beats) != len(durations) or not beats:
        raise ShortsError("Impact captions and durations must match")
    events: list[str] = []
    start = 0.0
    for beat, duration in zip(beats, durations, strict=True):
        end = start + duration
        caption = ass_escape(wrap_caption(beat["text"], width=36, max_lines=2))
        events.append(
            f"Dialogue: 2,{seconds_to_ass(start)},{seconds_to_ass(end)},Impact,,0,0,0,,"
            fr"{{\an5\pos(540,780)\fad(70,100)}}{caption}"
        )
        start = end
    return fr"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Impact,Poppins SemiBold,54,&H00FFFFFF,&H00FFFFFF,&HC8000000,&H50000000,0,0,0,0,100,100,0,0,1,3,1,5,95,95,0,1
Style: Channel,Poppins SemiBold,28,&H38FFFFFF,&H38FFFFFF,&H90000000,&H40000000,-1,0,0,0,100,100,1,0,1,2,0,2,60,60,125,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
Dialogue: 3,0:00:00.00,{seconds_to_ass(sum(durations))},Channel,,0,0,0,,{{\an2\pos(540,1700)}}{ass_escape(channel_name)}
"""


def build_ass_subtitles(entry: dict[str, str], channel_name: str) -> str:
    """Build staged, animated subtitles for the four-part Short structure."""
    hook = ass_escape(wrap_quote(make_hook(entry), width=24, max_lines=2))
    quote = ass_escape(wrap_quote(entry["quote"], width=32, max_lines=5))
    insight = ass_escape(wrap_quote(entry["insight"], width=34, max_lines=4))
    channel = ass_escape(channel_name)
    return fr"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,Poppins SemiBold,76,&H0000D7FF,&H0000D7FF,&HCC000000,&H80000000,-1,0,0,0,100,100,1,0,1,5,1,5,90,90,0,1
Style: Quote,Poppins SemiBold,52,&H00FFFFFF,&H00FFFFFF,&HCC000000,&H78000000,-1,0,0,0,100,100,0,0,1,4,1,5,90,90,0,1
Style: Label,Poppins SemiBold,30,&H0000D7FF,&H0000D7FF,&HCC000000,&H70000000,-1,0,0,0,100,100,2,0,1,3,0,5,90,90,0,1
Style: Action,Poppins SemiBold,46,&H00FFFFFF,&H00FFFFFF,&HCC000000,&H78000000,-1,0,0,0,100,100,0,0,1,4,1,5,90,90,0,1
Style: CTA,Poppins SemiBold,54,&H00FFFFFF,&H00FFFFFF,&HCC000000,&H80000000,-1,0,0,0,100,100,1,0,1,4,1,5,90,90,0,1
Style: Channel,Poppins SemiBold,30,&H10FFFFFF,&H10FFFFFF,&H60000000,&H50000000,-1,0,0,0,100,100,1,0,1,3,1,2,60,60,125,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 2,0:00:00.00,0:00:02.70,Hook,,0,0,0,,{{\fad(180,220)\fscx112\fscy112\t(0,300,\fscx100\fscy100)}}{hook}
Dialogue: 1,0:00:02.25,0:00:10.40,Quote,,0,0,0,,{{\fad(250,300)\fscx104\fscy104\t(0,350,\fscx100\fscy100)}}{quote}
Dialogue: 2,0:00:09.85,0:00:16.75,Label,,0,0,0,,{{\fad(220,250)\pos(540,690)}}DO THIS TODAY
Dialogue: 1,0:00:09.85,0:00:16.75,Action,,0,0,0,,{{\fad(220,250)\pos(540,1010)}}{insight}
Dialogue: 2,0:00:16.20,0:00:20.00,CTA,,0,0,0,,{{\fad(220,500)\fscx108\fscy108\t(0,350,\fscx100\fscy100)}}SAVE THIS FOR TOMORROW
Dialogue: 3,0:00:00.00,0:00:20.00,Channel,,0,0,0,,{{\an2\pos(540,1700)}}{channel}
"""


def build_metadata(
    entry: dict[str, str],
    *,
    creator_name: str,
    source_url: str,
    channel_name: str,
    privacy_status: str,
    music_name: str,
    music_creator: str = "Unknown creator",
    music_source_url: str = "",
    music_license: str = "CC0",
) -> dict[str, Any]:
    if privacy_status not in {"private", "unlisted", "public"}:
        raise ShortsError(f"Invalid privacy status: {privacy_status}")
    quote = entry["quote"].strip()
    insight = entry["insight"].strip()
    return {
        "quote_id": entry["id"],
        "quote": quote,
        "insight": insight,
        "category": entry["category"],
        "pexels_search": entry["pexels_search"],
        "pexels_creator": creator_name,
        "pexels_source_url": source_url,
        "music_file": music_name,
        "music_creator": music_creator,
        "music_source_url": music_source_url,
        "music_license": music_license,
        "channel_name": channel_name,
        "title": make_title(quote),
        "description": (
            f"{quote}\n\nTakeaway: {insight}\n\n"
            f"Footage by {creator_name} on Pexels: {source_url}\n"
            f"Music: {music_name} by {music_creator} "
            f"({music_license}): {music_source_url}\n\n"
            f"{HASHTAGS}"
        ),
        "tags": [
            "motivation",
            "discipline",
            "success",
            "mindset",
            "self improvement",
            entry["category"],
            "shorts",
        ],
        "category_id": "22",
        "made_for_kids": False,
        "privacy_status": privacy_status,
        "duration_seconds": VIDEO_SECONDS,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def build_story_metadata(
    story: dict[str, Any],
    *,
    hook: str,
    title: str,
    beats: list[dict[str, str]],
    duration: float,
    assets: list[dict[str, Any]],
    channel_name: str,
    privacy_status: str,
    music_asset: dict[str, Any],
) -> dict[str, Any]:
    """Build concise YouTube metadata plus analytics-ready creative fields."""
    if privacy_status not in {"private", "unlisted", "public"}:
        raise ShortsError(f"Invalid privacy status: {privacy_status}")
    safe_title = re.sub(r"\s+", " ", title).strip()[:100]
    payoff = beats[-1]["text"]
    footage_credits = "\n".join(
        f"{index}. {asset['creator_name']} - {asset['source_url']}"
        for index, asset in enumerate(assets, start=1)
    )
    content_label = "motivational quote" if story.get("quote_text") else "motivational micro-story"
    description = (
        f"{payoff}\n\n"
        f"Original {content_label}.\n\n"
        f"Footage on Pexels:\n{footage_credits}\n"
        f"Music: {music_asset['title']} by {music_asset['creator']} "
        f"({music_asset['license']}): {music_asset['source_url']}\n\n"
        "#motivation #selfimprovement #shorts"
    )
    return {
        "quote_id": story["id"],
        "story_id": story["id"],
        "catalog_file": story.get("catalog_file", "data/stories.json"),
        "content_pillar": story["pillar"],
        "topic": story["topic"],
        "theme": story["theme"],
        "perspective": story["perspective"],
        "protagonist_type": story["protagonist"],
        "hook_type": story["hook_type"],
        "hook_text": hook,
        "ending_concept": story["ending_concept"],
        "key_phrases": story["key_phrases"],
        "duration_seconds": round(duration, 2),
        "title": safe_title,
        "script": story.get("quote_text") or story_script(story, hook),
        "caption_beats": beats,
        "visual_searches": [beat["visual_search"] for beat in beats],
        "pexels_assets": [
            {
                "creator": asset["creator_name"],
                "source_url": asset["source_url"],
                "search_used": asset["search_used"],
            }
            for asset in assets
        ],
        "music_file": music_asset["title"],
        "music_creator": music_asset["creator"],
        "music_source_url": music_asset["source_url"],
        "music_license": music_asset["license"],
        "music_search_used": music_asset["search_used"],
        "channel_name": channel_name,
        "description": description,
        "tags": [story["topic"], story["theme"], "motivation", "self improvement", "shorts"],
        "category_id": "22",
        "made_for_kids": False,
        "privacy_status": privacy_status,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def valid_https_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.netloc)
    except ValueError:
        return False


def video_file_score(item: dict[str, Any]) -> tuple[float, float]:
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    ratio_penalty = abs((width / height if height else 99) - (9 / 16))
    size_penalty = abs(width - WIDTH) + abs(height - HEIGHT)
    landscape_penalty = 10 if width >= height else 0
    return (landscape_penalty + ratio_penalty, size_penalty)


def suitable_video_files(videos: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for video in videos:
        creator = video.get("user") or {}
        files: list[dict[str, Any]] = []
        for media in video.get("video_files") or []:
            link = str(media.get("link") or "")
            file_type = str(media.get("file_type") or "")
            width = int(media.get("width") or 0)
            height = int(media.get("height") or 0)
            if (
                not valid_https_url(link)
                or file_type != "video/mp4"
                or width < 540
                or height < 960
            ):
                continue
            files.append(
                {
                    "download_url": link,
                    "width": width,
                    "height": height,
                    "creator_name": str(creator.get("name") or "Pexels contributor"),
                    "source_url": str(video.get("url") or "https://www.pexels.com/videos/"),
                    "score": video_file_score(media),
                }
            )
        if files:
            candidates.append(min(files, key=lambda value: value["score"]))
    return sorted(candidates, key=lambda value: value["score"])


def search_pexels_clips(
    phrase: str,
    *,
    api_key: str,
    count: int = CLIP_COUNT,
    excluded_sources: set[str] | None = None,
    rng: random.Random | random.SystemRandom | None = None,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    chooser = rng or random.SystemRandom()
    client = session or http_session()
    errors: list[str] = []
    phrases = [phrase]
    if phrase.casefold() != FALLBACK_SEARCH.casefold():
        phrases.append(FALLBACK_SEARCH)
    selected_assets: list[dict[str, Any]] = []
    seen_sources: set[str] = set(excluded_sources or ())
    seen_creators: set[str] = set()
    for query in phrases:
        try:
            response = client.get(
                PEXELS_SEARCH_URL,
                headers={"Authorization": api_key},
                params={
                    "query": query,
                    "orientation": "portrait",
                    "size": "medium",
                    "locale": "en-US",
                    "per_page": 40,
                },
                timeout=(10, 45),
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            payload = response.json()
            candidates = suitable_video_files(payload.get("videos") or [])
            pool = [item for item in candidates[:20] if item["source_url"] not in seen_sources]
            chooser.shuffle(pool)
            for prefer_new_creator in (True, False):
                for selected in pool:
                    creator_key = selected["creator_name"].casefold()
                    if selected["source_url"] in seen_sources:
                        continue
                    if prefer_new_creator and creator_key in seen_creators:
                        continue
                    selected["search_used"] = query
                    selected_assets.append(selected)
                    seen_sources.add(selected["source_url"])
                    seen_creators.add(creator_key)
                    if len(selected_assets) == count:
                        return selected_assets
            errors.append(f"no suitable portrait MP4 results for {query!r}")
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"{query!r}: {exc}")
    raise ShortsError(
        f"Pexels search found only {len(selected_assets)} of {count} distinct clips; "
        + "; ".join(errors)
    )


def search_pexels_for_beats(
    beats: list[dict[str, str]],
    *,
    api_key: str,
    rng: random.Random | random.SystemRandom | None = None,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Choose one relevant portrait asset per story beat, avoiding repeats."""
    chooser = rng or random.SystemRandom()
    client = session or http_session()
    assets: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for index, beat in enumerate(beats):
        query = beat["visual_search"]
        try:
            asset = search_pexels_clips(
                query,
                api_key=api_key,
                count=1,
                excluded_sources=seen_sources,
                rng=chooser,
                session=client,
            )[0]
        except ShortsError:
            # A relevant repeated source is preferable to an unrelated random clip.
            asset = search_pexels_clips(
                query,
                api_key=api_key,
                count=1,
                rng=chooser,
                session=client,
            )[0]
        asset["beat_index"] = index
        seen_sources.add(asset["source_url"])
        assets.append(asset)
    return assets


def search_pexels(
    phrase: str,
    *,
    api_key: str,
    rng: random.Random | random.SystemRandom | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Backward-compatible single-result helper."""
    return search_pexels_clips(
        phrase, api_key=api_key, count=1, rng=rng, session=session
    )[0]


def download_file(url: str, destination: Path, *, session: requests.Session | None = None) -> None:
    if not valid_https_url(url):
        raise ShortsError("Pexels returned an invalid download URL")
    client = session or http_session()
    try:
        with client.get(url, stream=True, timeout=(10, 120)) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type and "video" not in content_type and "octet-stream" not in content_type:
                raise ShortsError(f"Pexels download returned unexpected content type: {content_type}")
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
    except requests.RequestException as exc:
        raise ShortsError(f"Unable to download Pexels footage: {exc}") from exc
    if not destination.exists() or destination.stat().st_size < 1024:
        raise ShortsError("Downloaded Pexels footage is empty or invalid")


def suitable_openverse_audio(
    results: Iterable[dict[str, Any]],
    *,
    minimum_seconds: float = 20,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in results:
        download_url = str(item.get("url") or "")
        source_url = str(item.get("foreign_landing_url") or "")
        license_code = str(item.get("license") or "").casefold()
        duration_ms = int(item.get("duration") or 0)
        if (
            not valid_https_url(download_url)
            or not valid_https_url(source_url)
            or license_code not in OPENVERSE_LICENSES
            or duration_ms < minimum_seconds * 1000
        ):
            continue
        candidates.append(
            {
                "id": str(item.get("id") or ""),
                "download_url": download_url,
                "title": str(item.get("title") or "Sad piano").strip(),
                "creator": str(item.get("creator") or "Openverse contributor").strip(),
                "source_url": source_url,
                "license": license_code.upper(),
                "duration_ms": duration_ms,
            }
        )
    return candidates


def search_openverse_audio(
    *,
    queries: Iterable[str] | None = None,
    minimum_seconds: float = MAX_SECONDS,
    rng: random.Random | random.SystemRandom | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    chooser = rng or random.SystemRandom()
    client = session or http_session()
    client_id = os.environ.get("OPENVERSE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("OPENVERSE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ShortsError("OPENVERSE_CLIENT_ID and OPENVERSE_CLIENT_SECRET are required")
    try:
        token_response = client.post(
            OPENVERSE_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=(10, 30),
        )
        token_response.raise_for_status()
        access_token = str(token_response.json().get("access_token") or "").strip()
    except (requests.RequestException, ValueError) as exc:
        raise ShortsError(f"Openverse authentication failed: {exc}") from exc
    if not access_token:
        raise ShortsError("Openverse authentication returned no access token")

    # A mood search can be too specific to return a long CC0/PDM recording.
    # Always keep broad motivational searches as a fallback so one
    # sparse Openverse query cannot stop the scheduled upload.
    story_queries = list(dict.fromkeys(queries or ()))
    fallback_queries = [query for query in MUSIC_SEARCHES if query not in story_queries]
    chooser.shuffle(story_queries)
    chooser.shuffle(fallback_queries)
    search_queries = [*story_queries, *fallback_queries]
    errors: list[str] = []
    for query in search_queries:
        try:
            response = client.get(
                OPENVERSE_AUDIO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "q": query,
                    "license": "cc0,pdm",
                    "page_size": 50,
                    "mature": "false",
                    "filter_dead": "true",
                },
                timeout=(10, 45),
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            candidates = suitable_openverse_audio(
                response.json().get("results") or [], minimum_seconds=minimum_seconds
            )
            if candidates:
                selected = chooser.choice(candidates)
                selected["search_used"] = query
                return selected
            errors.append(f"no suitable CC0/Public Domain results for {query!r}")
        except (requests.RequestException, ValueError, TypeError) as exc:
            errors.append(f"{query!r}: {exc}")
    raise ShortsError("Openverse motivational-music search failed; " + "; ".join(errors))


def download_audio(
    url: str,
    destination: Path,
    *,
    session: requests.Session | None = None,
) -> None:
    if not valid_https_url(url):
        raise ShortsError("Openverse returned an invalid audio URL")
    client = session or http_session()
    try:
        with client.get(url, stream=True, timeout=(10, 120)) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type and "audio" not in content_type and "octet-stream" not in content_type:
                raise ShortsError(
                    f"Openverse audio download returned unexpected content type: {content_type}"
                )
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
    except requests.RequestException as exc:
        raise ShortsError(f"Unable to download Openverse audio: {exc}") from exc
    if not destination.exists() or destination.stat().st_size < 4096:
        raise ShortsError("Downloaded Openverse audio is empty or invalid")


def locate_font() -> Path:
    if POPPINS_FONT_PATH.is_file():
        return POPPINS_FONT_PATH
    raise ShortsError(f"Bundled Poppins font is missing: {POPPINS_FONT_PATH}")


def ffmpeg_filter_path(path: Path) -> str:
    value = path.resolve().as_posix()
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def run_ffmpeg(
    footage: list[Path],
    music: Path,
    narration: Path,
    subtitles_file: Path,
    output: Path,
    beat_durations: list[float] | None = None,
) -> None:
    durations = beat_durations or [7.0] * len(footage)
    if not footage or len(footage) != len(durations):
        raise ShortsError("Footage clips and beat durations must be non-empty and match")
    total_seconds = sum(durations)
    if not IMPACT_MIN_SECONDS <= total_seconds <= IMPACT_MAX_SECONDS + 0.1:
        raise ShortsError(f"Rendered duration {total_seconds:.1f}s is outside the safe range")
    font = locate_font()
    subtitles_path = ffmpeg_filter_path(subtitles_file)
    fonts_dir = ffmpeg_filter_path(font.parent)
    filters: list[str] = []
    for index, duration in enumerate(durations):
        clip_duration = duration + (TRANSITION_SECONDS if index < len(durations) - 1 else 0)
        punch_scale = 1080 + index * 65
        punch_height = 1920 + index * 116
        filters.append(
            f"[{index}:v]scale={punch_scale}:{punch_height}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT}:(iw-ow)/2:(ih-oh)/2,fps={FPS},"
            f"trim=duration={clip_duration:.3f},"
            f"setpts=PTS-STARTPTS[v{index}]"
        )
    current = "v0"
    elapsed = durations[0]
    for index in range(1, len(durations)):
        output_label = f"vx{index}"
        filters.append(
            f"[{current}][v{index}]xfade=transition=fade:duration={TRANSITION_SECONDS}:"
            f"offset={elapsed:.3f}[{output_label}]"
        )
        current = output_label
        elapsed += durations[index]
    filters.append(
        f"[{current}]hue=s=0,eq=contrast=1.24:brightness=-0.055,"
        "unsharp=5:5:0.65:3:3:0.25,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.06:t=fill,"
        f"subtitles='{subtitles_path}':fontsdir='{fonts_dir}',"
        f"trim=duration={total_seconds:.3f},format=yuv420p[v]"
    )
    music_index = len(footage)
    narration_index = music_index + 1
    filters.append(
        f"[{music_index}:a]volume={MUSIC_MIX_VOLUME},afade=t=in:st=0:d=0.45,"
        f"afade=t=out:st={max(0, total_seconds - 1.1):.3f}:d=1.1,"
        f"atrim=duration={total_seconds:.3f},asetpts=PTS-STARTPTS[music];"
        f"[{narration_index}:a]highpass=f=75,lowpass=f=12000,"
        "loudnorm=I=-16:TP=-1.5:LRA=11,asplit=2[voice_sc][voice_mix];"
        f"[music][voice_sc]sidechaincompress=threshold={MUSIC_DUCK_THRESHOLD}:"
        f"ratio={MUSIC_DUCK_RATIO}:"
        "attack=15:release=240[ducked];"
        "[ducked][voice_mix]amix=inputs=2:duration=longest:normalize=0,"
        "loudnorm=I=-14:TP=-2:LRA=7,"
        f"alimiter=limit=0.79:level=false,atrim=duration={total_seconds:.3f}[a]"
    )
    video_filter = ";".join(filters)
    command = ["ffmpeg", "-hide_banner", "-y"]
    for clip in footage:
        command.extend(["-stream_loop", "-1", "-i", str(clip)])
    command.extend([
        "-stream_loop", "-1", "-i", str(music),
        "-i", str(narration),
        "-filter_complex",
        video_filter,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-t",
        f"{total_seconds:.3f}",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "21",
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(output),
    ])
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.splitlines()[-40:])
        raise ShortsError(f"FFmpeg rendering failed:\n{tail}")
    if not output.exists() or output.stat().st_size < 10_000:
        raise ShortsError("FFmpeg completed without producing a valid MP4")


def audio_duration(path: Path) -> float:
    if path.suffix.casefold() == ".wav":
        try:
            with wave.open(str(path), "rb") as wav_file:
                return wav_file.getnframes() / wav_file.getframerate()
        except (wave.Error, OSError, ZeroDivisionError) as exc:
            raise ShortsError(f"Unable to read narration WAV: {exc}") from exc
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        text=True,
        capture_output=True,
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise ShortsError(f"Unable to read narration duration: {result.stderr.strip()}") from exc
    if result.returncode != 0 or duration <= 0:
        raise ShortsError("TTS produced invalid narration audio")
    return duration


def synthesize_narration(text: str, output: Path, voice_file: Path | None = None) -> dict[str, Any]:
    """Create local narration without an API key and return auditable voice metadata."""
    if voice_file:
        if not voice_file.is_file():
            raise ShortsError(f"Voice file does not exist: {voice_file}")
        shutil.copyfile(voice_file, output)
        voice_name = "Local smoke-test narration"
        voice_license = "Local test file"
    else:
        model = TTS_MODEL_DIR / f"{TTS_VOICE}.onnx"
        config = TTS_MODEL_DIR / f"{TTS_VOICE}.onnx.json"
        if not model.is_file() or model.stat().st_size < 50_000_000 or not config.is_file():
            raise ShortsError(
                f"Piper voice {TTS_VOICE} is missing; run "
                f"python -m piper.download_voices --data-dir {TTS_MODEL_DIR} {TTS_VOICE}"
            )
        command = [
            sys.executable, "-m", "piper", "-m", TTS_VOICE,
            "--data-dir", str(TTS_MODEL_DIR), "-f", str(output),
            "--sentence-silence", "0.12", "--", text,
        ]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode != 0:
            tail = "\n".join(result.stderr.splitlines()[-25:])
            raise ShortsError(f"Piper narration failed:\n{tail}")
        voice_name = TTS_VOICE
        voice_license = "CC0 voice dataset; Piper engine GPL-3.0"
    duration = audio_duration(output)
    if duration > MAX_SECONDS:
        speed = min(2.0, duration / (MAX_SECONDS - 0.4))
        fitted = output.with_name("narration-fitted.wav")
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-y", "-i", str(output), "-af", f"atempo={speed:.5f}", str(fitted)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise ShortsError("Unable to fit TTS narration inside 40 seconds")
        fitted.replace(output)
        duration = audio_duration(output)
    return {
        "name": voice_name,
        "license": voice_license,
        "source_url": "https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/joe/medium",
        "duration_seconds": round(duration, 3),
    }


def synthesize_impact_narration(
    beats: list[dict[str, str]], output: Path, voice_file: Path | None = None
) -> tuple[dict[str, Any], list[float]]:
    """Synthesize phrase-by-phrase with changing pace and energy."""
    if voice_file:
        asset = synthesize_narration(" ".join(beat["text"] for beat in beats), output, voice_file)
        weights = [max(1, len(beat["text"].split())) for beat in beats]
        total_weight = sum(weights)
        durations = [asset["duration_seconds"] * weight / total_weight for weight in weights]
        return asset, durations

    model = TTS_MODEL_DIR / f"{TTS_VOICE}.onnx"
    config = TTS_MODEL_DIR / f"{TTS_VOICE}.onnx.json"
    if not model.is_file() or model.stat().st_size < 50_000_000 or not config.is_file():
        raise ShortsError(f"Piper voice {TTS_VOICE} is missing or incomplete")
    from piper import PiperVoice, SynthesisConfig

    voice = PiperVoice.load(str(model), config_path=str(config))
    profiles = [
        SynthesisConfig(length_scale=0.95, noise_scale=0.62, noise_w_scale=0.78, volume=1.00),
        SynthesisConfig(length_scale=0.89, noise_scale=0.68, noise_w_scale=0.84, volume=1.18),
        SynthesisConfig(length_scale=0.92, noise_scale=0.72, noise_w_scale=0.90, volume=1.35),
    ]
    durations: list[float] = []
    with wave.open(str(output), "wb") as wav_file:
        for index, beat in enumerate(beats):
            before = wav_file.tell()
            profile = profiles[min(index, len(profiles) - 1)]
            voice.synthesize_wav(
                beat["text"], wav_file, syn_config=profile, set_wav_format=index == 0
            )
            pause = 0.10 if index < len(beats) - 1 else 0.22
            pause_frames = round(wav_file.getframerate() * pause)
            wav_file.writeframes(
                b"\x00" * pause_frames * wav_file.getsampwidth() * wav_file.getnchannels()
            )
            durations.append((wav_file.tell() - before) / wav_file.getframerate())
    total = sum(durations)
    if total > IMPACT_MAX_SECONDS:
        speed = min(1.35, total / (IMPACT_MAX_SECONDS - 0.25))
        fitted = output.with_name("narration-impact-fitted.wav")
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-y", "-i", str(output), "-af", f"atempo={speed:.5f}", str(fitted)],
            text=True, capture_output=True,
        )
        if result.returncode != 0:
            raise ShortsError("Unable to fit impact narration inside 14.5 seconds")
        fitted.replace(output)
        durations = [duration / speed for duration in durations]
        total = sum(durations)
    asset = {
        "name": TTS_VOICE,
        "license": "CC0 voice dataset; Piper engine GPL-3.0",
        "source_url": "https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/joe/medium",
        "duration_seconds": round(total, 3),
        "delivery": "phrase-level dynamic pace and emphasis",
    }
    return asset, durations


def write_metadata(metadata: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quote", default=os.environ.get("INPUT_QUOTE", ""))
    parser.add_argument("--search", default=os.environ.get("INPUT_PEXELS_SEARCH", ""))
    parser.add_argument(
        "--privacy",
        default=os.environ.get("INPUT_PRIVACY_STATUS", "private"),
        choices=("private", "unlisted", "public"),
    )
    parser.add_argument("--footage-file", type=Path, help="Local footage for offline smoke tests")
    parser.add_argument("--music-file", type=Path, help="Specific music for offline smoke tests")
    parser.add_argument("--voice-file", type=Path, help="Specific narration WAV for offline smoke tests")
    parser.add_argument(
        "--story-id",
        default=os.environ.get("INPUT_STORY_ID", ""),
        help="Render one catalog story without consuming it",
    )
    parser.add_argument("--seed", type=int, help="Deterministic selection for tests")
    return parser.parse_args()


def make_manual_story(text: str, search: str) -> dict[str, Any]:
    """Keep the existing manual quote input usable as a private test story."""
    visual = search or FALLBACK_SEARCH
    title = clean_manual_title = re.sub(r"\s+", " ", text).strip().strip('"')
    if len(clean_manual_title) > 58:
        title = clean_manual_title[:58].rsplit(" ", 1)[0].rstrip(".,;:!?")
    return {
        "id": "manual",
        "quote_text": text,
        "catalog_file": "data/quotes.json",
        "pillar": "transformation",
        "topic": "personal change",
        "theme": "starting over",
        "perspective": "you",
        "protagonist": "manual workflow subject",
        "hook_type": "manual_override",
        "hook_candidates": [text, text, text],
        "hook_visual": visual,
        "beats": [
            {"phase": "problem", "text": "For weeks, the same problem kept returning in a different disguise.", "visual_search": visual},
            {"phase": "problem", "text": "Planning felt safer than discovering whether the effort would work.", "visual_search": visual},
            {"phase": "problem", "text": "Another ordinary day nearly ended with the same promise.", "visual_search": visual},
            {"phase": "turn", "text": "Then one useful action replaced the speech about changing.", "visual_search": visual},
            {"phase": "turn", "text": "It was repeated quietly before confidence had time to arrive.", "visual_search": visual},
            {"phase": "turn", "text": "The result stayed small, but the evidence became difficult to ignore.", "visual_search": visual},
            {"phase": "payoff", "text": "The future moved when the promise finally became something visible.", "visual_search": visual},
        ],
        "title_candidates": [title, "The Promise That Became Visible"],
        "ending_concept": "action made change visible",
        "key_phrases": ["useful action", "visible promise"],
        "music_searches": list(MUSIC_SEARCHES),
    }


def quote_to_impact_story(entry: dict[str, str]) -> dict[str, Any]:
    """Adapt an original quote-bank entry to the cinematic impact renderer."""
    quote = entry["quote"].strip()
    return {
        "id": entry["id"],
        "quote_text": quote,
        "catalog_file": "data/quotes.json",
        "pillar": entry["category"],
        "topic": entry["category"],
        "theme": "motivational quote",
        "perspective": "you",
        "protagonist": "the viewer",
        "hook_type": "direct_motivation",
        "hook_candidates": [make_hook(entry)] * 3,
        "hook_visual": entry["pexels_search"],
        "title_candidates": [make_title(quote)],
        "ending_concept": entry["insight"],
        "key_phrases": [entry["category"], "take action"],
        "music_searches": list(MUSIC_SEARCHES),
    }


def main() -> None:
    args = parse_args()
    rng: random.Random | random.SystemRandom = (
        random.Random(args.seed) if args.seed is not None else random.SystemRandom()
    )
    channel_name = validate_channel_name(os.environ.get("CHANNEL_NAME", ""))
    if not shutil.which("ffmpeg"):
        raise ShortsError("ffmpeg is not installed or not on PATH")

    state = load_state()
    quote_override = re.sub(r"\s+", " ", args.quote).strip()
    if quote_override:
        selected = make_manual_story(quote_override, args.search.strip())
        hook = quote_override
        title = selected["title_candidates"][0]
        state_changed = False
    elif args.story_id:
        if args.story_id.startswith("m"):
            try:
                entry = next(quote for quote in load_quotes() if quote["id"] == args.story_id)
            except StopIteration as exc:
                raise ShortsError(f"Unknown quote id: {args.story_id}") from exc
            selected = quote_to_impact_story(entry)
            hook = make_hook(entry)
            title = selected["title_candidates"][0]
        else:
            try:
                stories = load_stories(STORIES_PATH)
                selected = next(story for story in stories if story["id"] == args.story_id)
            except StoryError as exc:
                raise ShortsError(str(exc)) from exc
            except StopIteration as exc:
                raise ShortsError(f"Unknown story id: {args.story_id}") from exc
            hook = select_hook(selected)
            title = select_title(selected)
        state_changed = False
    else:
        entry = select_quote(load_quotes(), state, rng=rng)
        selected = quote_to_impact_story(entry)
        hook = make_hook(entry)
        title = selected["title_candidates"][0]
        state_changed = True

    beats = impact_beats(selected, hook)
    if args.search.strip():
        beats = [{**beat, "visual_search": args.search.strip()} for beat in beats]
    duration_seconds = 12.0

    if args.music_file:
        if not args.music_file.is_file():
            raise ShortsError(f"Music file does not exist: {args.music_file}")
        music = args.music_file
        music_asset = {
            "title": music.name,
            "creator": "Local smoke test",
            "source_url": "https://openverse.org/",
            "license": "Local test file",
            "search_used": "local override",
        }
    else:
        music_asset = search_openverse_audio(
            queries=selected["music_searches"],
            minimum_seconds=IMPACT_MAX_SECONDS + 0.5,
            rng=rng,
        )
        music = Path()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_video = OUTPUT_DIR / "short.mp4"
    output_metadata = OUTPUT_DIR / "metadata.json"

    with tempfile.TemporaryDirectory(prefix="youtube-short-") as temp_name:
        temporary = Path(temp_name)
        narration = temporary / "narration.wav"
        voice_asset, durations = synthesize_impact_narration(beats, narration, args.voice_file)
        duration_seconds = sum(durations)
        if duration_seconds < IMPACT_MIN_SECONDS:
            durations[-1] += IMPACT_MIN_SECONDS - duration_seconds
        duration_seconds = sum(durations)
        if args.footage_file:
            if not args.footage_file.is_file():
                raise ShortsError(f"Footage file does not exist: {args.footage_file}")
            footage = [args.footage_file] * len(beats)
            assets = [{
                "creator_name": "Local smoke test",
                "source_url": "https://www.pexels.com/",
                "search_used": beat["visual_search"],
                "beat_index": index,
            } for index, beat in enumerate(beats)]
        else:
            api_key = os.environ.get("PEXELS_API_KEY", "").strip()
            if not api_key:
                raise ShortsError("PEXELS_API_KEY is required")
            primary_asset = search_pexels_clips(
                beats[0]["visual_search"], api_key=api_key, count=1, rng=rng
            )[0]
            primary_clip = temporary / "pexels-impact.mp4"
            download_file(primary_asset["download_url"], primary_clip)
            assets = [{**primary_asset, "beat_index": index} for index in range(len(beats))]
            footage = [primary_clip] * len(beats)

        if not args.music_file:
            music = temporary / "openverse-music.mp3"
            download_audio(music_asset["download_url"], music)

        subtitles_file = temporary / "captions.ass"
        subtitles_file.write_text(
            build_impact_subtitles(beats, durations, channel_name),
            encoding="utf-8",
            newline="\n",
        )
        run_ffmpeg(footage, music, narration, subtitles_file, output_video, durations)

    metadata = build_story_metadata(
        selected,
        hook=hook,
        title=title,
        beats=beats,
        duration=duration_seconds,
        assets=assets,
        channel_name=channel_name,
        privacy_status=args.privacy,
        music_asset=music_asset,
    )
    metadata["tts_voice"] = voice_asset["name"]
    metadata["tts_license"] = voice_asset["license"]
    metadata["tts_source_url"] = voice_asset["source_url"]
    metadata["narration_duration_seconds"] = voice_asset["duration_seconds"]
    metadata["format"] = "impact_quote"
    metadata["script"] = " ".join(beat["text"] for beat in beats)
    metadata["quote_word_count"] = sum(len(beat["text"].split()) for beat in beats)
    metadata["visual_style"] = "high-contrast monochrome punch-in"
    metadata["audio_target_lufs"] = -14
    if args.story_id:
        metadata["quote_id"] = "manual"
        metadata["preview_story_id"] = selected["id"]
    write_metadata(metadata, output_metadata)
    if state_changed:
        save_state(state)
    print(f"Rendered {output_video.relative_to(ROOT)}")
    print(f"Metadata {output_metadata.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except ShortsError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
