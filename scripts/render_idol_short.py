#!/usr/bin/env python3
"""Render a 55–65 second Reddit-sourced K-pop idol facts Short."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

from scripts.ai_script import ScriptResult, generate_script
from scripts.reddit_source import (
    DEFAULT_SUBREDDITS,
    RedditClient,
    RedditSourceError,
    choose_idol,
    parse_subreddits,
    rank_clip_posts,
    reddit_post_url,
    select_fact_posts,
)
from scripts.render_short import (
    MUSIC_DUCK_RATIO,
    MUSIC_DUCK_THRESHOLD,
    MUSIC_MIX_VOLUME,
    TTS_MODEL_DIR,
    TTS_VOICE,
    ffmpeg_filter_path,
    locate_font,
    validate_channel_name,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
MUSIC_DIR = ROOT / "music"
STATE_PATH = ROOT / "data" / "reddit_state.json"
WIDTH = 1080
HEIGHT = 1920
FPS = 30
MIN_SECONDS = 55.0
MAX_SECONDS = 65.0
TARGET_NARRATION_SECONDS = 57.0
CUT_SECONDS = 4.6
TRANSITION_SECONDS = 0.08
MAX_DOWNLOAD_BYTES = 150 * 1024 * 1024
PINK_ASS = "&H00AE3DFF"
YELLOW_ASS = "&H003DE6FF"
RED_ASS = "&H00573DFF"
HIGHLIGHT_TERMS = {
    "first",
    "million",
    "billion",
    "record",
    "rich",
    "viral",
    "won",
    "youngest",
}


class IdolShortError(RuntimeError):
    """The idol Short could not be rendered safely."""


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "used_fact_urls": [], "used_clip_urls": [], "idol_history": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdolShortError(f"Unable to read Reddit state: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise IdolShortError("data/reddit_state.json must be a version 1 state object")
    return {
        "version": 1,
        "used_fact_urls": [str(value) for value in payload.get("used_fact_urls", [])][-500:],
        "used_clip_urls": [str(value) for value in payload.get("used_clip_urls", [])][-500:],
        "idol_history": [str(value) for value in payload.get("idol_history", [])][-60:],
    }


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)



def select_bundled_music(rng: random.Random | random.SystemRandom) -> tuple[Path, dict[str, Any]]:
    tracks = sorted(MUSIC_DIR.glob("*.mp3"))
    if not tracks:
        raise IdolShortError(f"No bundled music tracks found in {MUSIC_DIR}")
    music_path = rng.choice(tracks)
    return music_path, {
        "title": music_path.name,
        "creator": "Repository-bundled audio",
        "source_url": "https://github.com/Skip-me-not/horror-video-automation/tree/main/music",
        "license": "Bundled asset; verify publication rights",
        "search_used": "local deterministic selection",
    }


def clean_fact_title(title: str, idol: str) -> str:
    text = re.sub(r"\s+", " ", title).strip()
    text = re.sub(r"^(?:throwback|discussion|appreciation)\s*[:\-–]\s*", "", text, flags=re.I)
    text = re.sub(r"\[(?:discussion|appreciation|throwback)\]", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -–")
    if not text:
        raise IdolShortError("A selected Reddit fact has an empty title")
    if idol.casefold() not in text.casefold():
        text = f"{idol}: {text}"
    if text[-1] not in ".!":
        text += "."
    return text


def compact_count(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} million"
    if value >= 1_000:
        rounded = round(value / 1_000, 1)
        return f"{rounded:g} thousand"
    return str(value)


def build_segments(idol: str, facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(facts) not in {3, 4}:
        raise IdolShortError("A Short needs 3 or 4 selected Reddit facts")
    segments: list[dict[str, Any]] = [
        {
            "kind": "hook",
            "text": f"Here are {len(facts)} {idol} moments that made K-pop Reddit stop scrolling.",
        }
    ]
    for index, fact in enumerate(facts, start=1):
        title = clean_fact_title(fact["title"], idol)
        segments.append(
            {
                "kind": "fact",
                "fact_number": index,
                "text": (
                    f"Number {index}. {title} Redditors pushed that discussion to "
                    f"{compact_count(fact['score'])} upvotes and {compact_count(fact['num_comments'])} comments "
                    f"in r slash {fact['subreddit']}."
                ),
                "source_url": reddit_post_url(fact["permalink"]),
            }
        )
    segments.append(
        {
            "kind": "outro",
            "text": f"Which {idol} moment should be in part two? Comment it below and follow for the next idol.",
        }
    )
    return segments


def narration_text(segments: Iterable[dict[str, Any]]) -> str:
    return " ".join(str(segment["text"]).strip() for segment in segments)


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    whole_seconds, hundredths = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{hundredths:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def display_word(token: str) -> str:
    cleaned = re.sub(r"(^[^A-Za-z0-9$#]+|[^A-Za-z0-9$%!?.,'\-]+$)", "", token)
    return cleaned or token


def word_colour(token: str) -> str:
    plain = re.sub(r"[^A-Za-z0-9]", "", token).casefold()
    if any(character.isdigit() for character in token):
        return YELLOW_ASS
    if plain in {"stop", "secret", "warning", "never"}:
        return RED_ASS
    if plain in HIGHLIGHT_TERMS:
        return YELLOW_ASS
    return PINK_ASS


def segment_durations(segments: list[dict[str, Any]], narration_seconds: float) -> list[float]:
    weights = [max(1, word_count(segment["text"])) for segment in segments]
    total = sum(weights)
    return [narration_seconds * weight / total for weight in weights]


def build_word_captions(segments: list[dict[str, Any]], narration_seconds: float) -> str:
    """Create the reference's one-word-at-a-time pink caption treatment."""
    events: list[str] = []
    elapsed = 0.0
    for segment, duration in zip(segments, segment_durations(segments, narration_seconds), strict=True):
        words = [display_word(word) for word in segment["text"].split()]
        weights = [max(1.0, len(re.sub(r"\W", "", word)) ** 0.36) for word in words]
        unit = duration / sum(weights)
        for word, weight in zip(words, weights, strict=True):
            end = elapsed + unit * weight
            colour = word_colour(word)
            safe_word = ass_escape(word)
            animation = r"{\an5\pos(540,1120)\fscx108\fscy108\t(0,100,\fscx100\fscy100)"
            events.append(
                f"Dialogue: 2,{ass_time(elapsed)},{ass_time(end)},Word,,0,0,0,,"
                f"{animation}\\c{colour}}}{safe_word}"
            )
            elapsed = end
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,Poppins SemiBold,62,{PINK_ASS},{PINK_ASS},&HDD000000,&H50000000,-1,0,0,0,100,100,0,0,1,6,2,5,80,80,0,1
Style: Brand,Poppins SemiBold,27,&H38FFFFFF,&H38FFFFFF,&H90000000,&H40000000,-1,0,0,0,100,100,1,0,1,2,0,2,60,60,110,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""


def wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as audio:
            return audio.getnframes() / audio.getframerate()
    except (OSError, wave.Error, ZeroDivisionError) as exc:
        raise IdolShortError(f"Unable to read narration WAV: {exc}") from exc


def synthesize_narration(text: str, output: Path, voice_file: Path | None = None) -> dict[str, Any]:
    if voice_file:
        if not voice_file.is_file():
            raise IdolShortError(f"Voice file does not exist: {voice_file}")
        shutil.copyfile(voice_file, output)
        voice_name = "Local test narration"
        voice_license = "Local test file"
    else:
        model = TTS_MODEL_DIR / f"{TTS_VOICE}.onnx"
        config = TTS_MODEL_DIR / f"{TTS_VOICE}.onnx.json"
        if not model.is_file() or model.stat().st_size < 50_000_000 or not config.is_file():
            raise IdolShortError(f"Piper voice {TTS_VOICE} is missing or incomplete")
        command = [
            os.sys.executable,
            "-m",
            "piper",
            "-m",
            TTS_VOICE,
            "--data-dir",
            str(TTS_MODEL_DIR),
            "-f",
            str(output),
            "--sentence-silence",
            "0.16",
            "--",
            text,
        ]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode != 0:
            tail = "\n".join(result.stderr.splitlines()[-25:])
            raise IdolShortError(f"Piper narration failed:\n{tail}")
        voice_name = TTS_VOICE
        voice_license = "CC0 voice dataset; Piper engine GPL-3.0"

    original_seconds = wav_duration(output)
    speed = original_seconds / TARGET_NARRATION_SECONDS
    if not 0.86 <= speed <= 1.16:
        speed = min(1.16, max(0.86, speed))
    if abs(speed - 1.0) >= 0.015:
        fitted = output.with_name("narration-fitted.wav")
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-y", "-i", str(output), "-af", f"atempo={speed:.5f}", str(fitted)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise IdolShortError("Unable to fit narration pace inside the one-minute format")
        fitted.replace(output)
    duration = wav_duration(output)
    if not 46 <= duration <= 63.5:
        raise IdolShortError(
            f"Narration is {duration:.1f}s; expected 46–63.5s. Use 4 richer facts or shorter source titles."
        )
    return {
        "name": voice_name,
        "license": voice_license,
        "duration_seconds": round(duration, 3),
        "source_url": "https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/joe/medium",
    }


def valid_reddit_media_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and (
        host == "v.redd.it" or host.endswith(".v.redd.it") or host.endswith(".redditmedia.com")
    )


def reddit_hls_url(value: str) -> str:
    if not valid_reddit_media_url(value):
        return ""
    parsed = urlparse(value)
    if (parsed.hostname or "").casefold() != "v.redd.it":
        return ""
    media_id = parsed.path.strip("/").split("/", 1)[0]
    return f"https://v.redd.it/{media_id}/HLSPlaylist.m3u8" if media_id else ""


def reddit_manifest_urls(value: str) -> list[str]:
    hls = reddit_hls_url(value)
    if not hls:
        return []
    base = hls.rsplit("/", 1)[0]
    return [hls, f"{base}/DASHPlaylist.mpd"]


def download_reddit_video(
    url: str,
    destination: Path,
    *,
    user_agent: str,
    session: requests.Session | None = None,
) -> None:
    if not valid_reddit_media_url(url):
        raise IdolShortError("Reddit returned an unsupported video URL")
    client = session or requests.Session()
    headers = {
        "User-Agent": user_agent,
        "Referer": "https://www.reddit.com/",
        "Accept": "video/mp4,application/octet-stream,*/*;q=0.8",
    }
    written = 0
    direct_error = ""
    try:
        with client.get(url, stream=True, headers=headers, timeout=(10, 120)) as response:
            response.raise_for_status()
            if not valid_reddit_media_url(response.url):
                raise IdolShortError("Reddit video redirected outside approved media hosts")
            content_type = response.headers.get("Content-Type", "").casefold()
            if content_type and "video" not in content_type and "octet-stream" not in content_type:
                raise IdolShortError(f"Reddit returned unexpected media type: {content_type}")
            try:
                declared = int(response.headers.get("Content-Length") or 0)
            except ValueError:
                declared = 0
            if declared > MAX_DOWNLOAD_BYTES:
                raise IdolShortError("Reddit clip exceeds the 150 MB download limit")
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > MAX_DOWNLOAD_BYTES:
                        raise IdolShortError("Reddit clip exceeded the 150 MB download limit")
                    handle.write(chunk)
    except requests.RequestException as exc:
        direct_error = str(exc)
        destination.unlink(missing_ok=True)

    if written >= 10_000:
        return

    manifest_urls = reddit_manifest_urls(url)
    if not manifest_urls:
        raise IdolShortError(f"Unable to download Reddit video: {direct_error or 'empty response'}")
    ffmpeg_headers = f"User-Agent: {user_agent}\r\nReferer: https://www.reddit.com/\r\n"
    manifest_errors: list[str] = []
    for manifest_url in manifest_urls:
        destination.unlink(missing_ok=True)
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-protocol_whitelist",
                "https,tls,tcp,http,crypto",
                "-headers",
                ffmpeg_headers,
                "-i",
                manifest_url,
                "-t",
                "180",
                "-map",
                "0:v:0",
                "-an",
                "-c:v",
                "copy",
                "-movflags",
                "+faststart",
                str(destination),
            ],
            text=True,
            capture_output=True,
        )
        size = destination.stat().st_size if destination.exists() else 0
        if result.returncode == 0 and 10_000 <= size <= MAX_DOWNLOAD_BYTES:
            return
        destination.unlink(missing_ok=True)
        tail = " | ".join(result.stderr.splitlines()[-3:])
        manifest_errors.append(f"{manifest_url.rsplit('/', 1)[-1]}: {tail}")
    raise IdolShortError(
        "Reddit direct media plus HLS/DASH manifests failed. "
        f"Direct: {direct_error or 'empty response'}. " + "; ".join(manifest_errors)
    )


def download_clip_pool(
    candidates: list[dict[str, Any]],
    *,
    count: int,
    directory: Path,
    user_agent: str,
    downloader=download_reddit_video,
) -> tuple[list[Path], list[dict[str, Any]]]:
    local_clips: list[Path] = []
    selected: list[dict[str, Any]] = []
    errors: list[str] = []
    max_attempts = min(len(candidates), max(12, count * 4))
    for attempt, post in enumerate(candidates[:max_attempts], start=1):
        clip_path = directory / f"reddit-{len(local_clips) + 1}.mp4"
        try:
            downloader(post["video_url"], clip_path, user_agent=user_agent)
        except IdolShortError as exc:
            errors.append(f"attempt {attempt}: {exc}")
            clip_path.unlink(missing_ok=True)
            print(f"Skipping unavailable Reddit clip {attempt}/{max_attempts}")
            continue
        selected.append(post)
        local_clips.append(clip_path)
        if len(local_clips) == count:
            return local_clips, selected
    recent_errors = " | ".join(errors[-3:])
    raise IdolShortError(
        f"Downloaded only {len(local_clips)} of {count} Reddit clips after "
        f"{max_attempts} attempts. {recent_errors}"
    )


def render_video(
    clips: list[Path],
    music: Path,
    narration: Path,
    captions: Path,
    output: Path,
    *,
    duration: float,
) -> None:
    if not clips:
        raise IdolShortError("At least one Reddit clip is required")
    if not MIN_SECONDS <= duration <= MAX_SECONDS:
        raise IdolShortError(f"Output duration {duration:.1f}s is outside 55–65 seconds")
    segment_count = max(len(clips), math.ceil(duration / CUT_SECONDS))
    sequence = [
        clips[(index * (len(clips) - 1)) % len(clips)]
        for index in range(segment_count)
    ]
    segment_seconds = duration / segment_count
    font = locate_font()
    filters: list[str] = []
    for index in range(segment_count):
        clip_duration = segment_seconds + (TRANSITION_SECONDS if index < segment_count - 1 else 0)
        zoom = 1.0 + (index % 3) * 0.025
        filters.extend(
            [
                f"[{index}:v]split=2[bg{index}][fg{index}]",
                f"[bg{index}]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},gblur=sigma=32:steps=2[blur{index}]",
                f"[fg{index}]scale='min({WIDTH},iw*{zoom:.3f})':'min({HEIGHT},ih*{zoom:.3f})':"
                f"force_original_aspect_ratio=decrease,setsar=1[front{index}]",
                f"[blur{index}][front{index}]overlay=(W-w)/2:(H-h)/2,"
                f"eq=contrast=1.06:saturation=1.05,trim=duration={clip_duration:.3f},"
                f"fps={FPS},setpts=PTS-STARTPTS[v{index}]",
            ]
        )
    current = "v0"
    elapsed = segment_seconds
    for index in range(1, segment_count):
        output_label = f"vx{index}"
        filters.append(
            f"[{current}][v{index}]xfade=transition=fade:duration={TRANSITION_SECONDS}:"
            f"offset={elapsed:.3f}[{output_label}]"
        )
        current = output_label
        elapsed += segment_seconds
    filters.append(
        f"[{current}]subtitles='{ffmpeg_filter_path(captions)}':"
        f"fontsdir='{ffmpeg_filter_path(font.parent)}',trim=duration={duration:.3f},format=yuv420p[v]"
    )
    music_index = segment_count
    narration_index = music_index + 1
    filters.extend(
        [
            f"[{music_index}:a]volume={MUSIC_MIX_VOLUME},afade=t=in:st=0:d=0.45,"
            f"afade=t=out:st={duration - 1.2:.3f}:d=1.2,atrim=duration={duration:.3f},"
            "asetpts=PTS-STARTPTS[music]",
            f"[{narration_index}:a]highpass=f=75,lowpass=f=12000,"
            "loudnorm=I=-16:TP=-1.5:LRA=11,asplit=2[voice_sc][voice_mix]",
            f"[music][voice_sc]sidechaincompress=threshold={MUSIC_DUCK_THRESHOLD}:"
            f"ratio={MUSIC_DUCK_RATIO}:attack=15:release=240[ducked]",
            "[ducked][voice_mix]amix=inputs=2:duration=longest:normalize=0,"
            f"loudnorm=I=-14:TP=-2:LRA=7,alimiter=limit=0.79:level=false,"
            f"atrim=duration={duration:.3f}[a]",
        ]
    )
    command = ["ffmpeg", "-hide_banner", "-y"]
    for clip in sequence:
        command.extend(["-stream_loop", "-1", "-i", str(clip)])
    command.extend(["-stream_loop", "-1", "-i", str(music), "-i", str(narration)])
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{duration:.3f}",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
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
        ]
    )
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.splitlines()[-50:])
        raise IdolShortError(f"FFmpeg idol render failed:\n{tail}")
    if not output.is_file() or output.stat().st_size < 100_000:
        raise IdolShortError("FFmpeg did not produce a valid idol Short")


def build_metadata(
    idol: str,
    facts: list[dict[str, Any]],
    clips: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    *,
    duration: float,
    privacy: str,
    music: dict[str, Any],
    voice: dict[str, Any],
    channel_name: str,
    script_result: ScriptResult | None = None,
) -> dict[str, Any]:
    fact_sources = [reddit_post_url(post["permalink"]) for post in facts]
    clip_sources = [reddit_post_url(post["permalink"]) for post in clips]
    credits = "\n".join(f"- {url}" for url in [*fact_sources, *clip_sources])
    title = f"{len(facts)} {idol} Moments Reddit Couldn't Stop Discussing #shorts"
    return {
        "title": title[:100],
        "description": (
            f"{len(facts)} Reddit discussions about {idol}, transformed with original narration and editing.\n\n"
            f"Reddit discussion and clip sources:\n{credits}\n\n"
            f"Music: {music['title']} by {music['creator']} ({music['license']}): {music['source_url']}\n\n"
            "Reddit popularity is a source signal, not independent fact verification. "
            "The narration is rewritten commentary; verify claims before publication.\n\n"
            "#kpop #idol #shorts"
        ),
        "tags": [idol, "kpop", "kpop facts", "idol facts", "reddit", "shorts"],
        "category_id": "24",
        "made_for_kids": False,
        "privacy_status": privacy,
        "format": "reddit_idol_short",
        "script_engine": script_result.engine if script_result else "legacy_editorial",
        "script_model": script_result.model if script_result else "none",
        "script_prompt_version": script_result.prompt_version if script_result else "legacy",
        "idol": idol,
        "fact_count": len(facts),
        "duration_seconds": round(duration, 2),
        "script": narration_text(segments),
        "caption_style": "one-word hot-pink captions with yellow/red emphasis",
        "visual_style": "4.6-second rapid cuts with blurred vertical fill",
        "fact_sources": fact_sources,
        "clip_sources": clip_sources,
        "source_scope": "Reddit only for facts and footage",
        "fact_verification": "Reddit discussion filtering with source attribution",
        "publication_mode": "automatic_public",
        "channel_name": channel_name,
        "music_file": music["title"],
        "music_creator": music["creator"],
        "music_source_url": music["source_url"],
        "music_license": music["license"],
        "tts_voice": voice["name"],
        "tts_license": voice["license"],
        "tts_source_url": voice["source_url"],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idol", default=os.environ.get("INPUT_IDOL", ""))
    parser.add_argument(
        "--fact-count",
        type=int,
        choices=(3, 4),
        default=int(os.environ.get("INPUT_FACT_COUNT", "4")),
    )
    parser.add_argument(
        "--subreddits",
        default=os.environ.get("INPUT_SUBREDDITS", ",".join(DEFAULT_SUBREDDITS)),
    )
    parser.add_argument(
        "--privacy",
        choices=("private", "unlisted", "public"),
        default=os.environ.get("INPUT_PRIVACY_STATUS", "public"),
    )
    parser.add_argument("--music-file", type=Path)
    parser.add_argument("--voice-file", type=Path)
    parser.add_argument("--seed", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not shutil.which("ffmpeg"):
        raise IdolShortError("ffmpeg is not installed or not on PATH")
    channel_name = validate_channel_name(os.environ.get("CHANNEL_NAME", ""))
    rng: random.Random | random.SystemRandom = (
        random.Random(args.seed) if args.seed is not None else random.SystemRandom()
    )
    state = load_state()
    idol = choose_idol(args.idol, used_idols=state["idol_history"], rng=rng)
    user_agent = (
        os.environ.get("REDDIT_USER_AGENT", "").strip()
        or "github:youtube-shorts-automation:v1.0 (by /u/young-standing)"
    )
    client = RedditClient(user_agent=user_agent)
    posts = client.discover(idol, parse_subreddits(args.subreddits))
    facts = select_fact_posts(
        posts,
        idol,
        count=args.fact_count,
        excluded_urls=state["used_fact_urls"],
    )
    clip_candidates = rank_clip_posts(
        posts,
        idol,
        excluded_urls=state["used_clip_urls"],
    )
    if len(clip_candidates) < args.fact_count:
        raise RedditSourceError(
            f"Reddit returned only {len(clip_candidates)} safe hosted {idol} clips; "
            f"need {args.fact_count}."
        )
    script_result = generate_script(
        idol,
        facts,
        mode="fallback",
    )
    segments = script_result.segments
    for index, segment in enumerate(segments):
        if segment["kind"] == "fact" and index - 1 < len(facts):
            segment["source_url"] = reddit_post_url(facts[index - 1]["permalink"])
    script = script_result.narration
    if not 95 <= word_count(script) <= 180:
        raise IdolShortError(f"Generated script has {word_count(script)} words; expected 95–180")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_video = OUTPUT_DIR / "short.mp4"
    output_metadata = OUTPUT_DIR / "metadata.json"
    with tempfile.TemporaryDirectory(prefix="reddit-idol-short-") as temp_name:
        temporary = Path(temp_name)
        narration = temporary / "narration.wav"
        voice = synthesize_narration(script, narration, args.voice_file)
        duration = min(MAX_SECONDS, max(MIN_SECONDS, voice["duration_seconds"] + 1.2))
        captions = temporary / "captions.ass"
        captions.write_text(
            build_word_captions(segments, voice["duration_seconds"]),
            encoding="utf-8",
            newline="\n",
        )
        local_clips, clips = download_clip_pool(
            clip_candidates,
            count=args.fact_count,
            directory=temporary,
            user_agent=user_agent,
        )

        if args.music_file:
            if not args.music_file.is_file():
                raise IdolShortError(f"Music file does not exist: {args.music_file}")
            music_path = args.music_file
            music_asset = {
                "title": args.music_file.name,
                "creator": "Local test asset",
                "source_url": "https://github.com/Skip-me-not/horror-video-automation/tree/main/music",
                "license": "Local test file",
                "search_used": "local override",
            }
        else:
            music_path, music_asset = select_bundled_music(rng)
        render_video(
            local_clips,
            music_path,
            narration,
            captions,
            output_video,
            duration=duration,
        )

    metadata = build_metadata(
        idol,
        facts,
        clips,
        segments,
        duration=duration,
        privacy=args.privacy,
        music=music_asset,
        voice=voice,
        channel_name=channel_name,
        script_result=script_result,
    )
    output_metadata.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    state["used_fact_urls"] = (
        state["used_fact_urls"] + [reddit_post_url(post["permalink"]) for post in facts]
    )[-500:]
    state["used_clip_urls"] = (
        state["used_clip_urls"] + [reddit_post_url(post["permalink"]) for post in clips]
    )[-500:]
    state["idol_history"] = (state["idol_history"] + [idol])[-60:]
    save_state(state)
    print(f"Rendered {output_video.relative_to(ROOT)}")
    print(f"Metadata {output_metadata.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except (IdolShortError, RedditSourceError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
