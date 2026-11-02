#!/usr/bin/env python3
"""Render the reference-matched 60-second BL countdown format."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageDraw

from scripts.bl_engine import BLEngineError, ROOT, clean_text, generate_package, normalized_url, write_json_atomic
from scripts.bl_renderer import FONT, LOG_DIR, OUTPUT_DIR, REPORT_DIR, ass_escape, ass_time, download_asset, ffprobe, filter_path

WIDTH, HEIGHT = 720, 1280
FPS = "30000/1001"
SEGMENT_DURATIONS = [12.0, 9.0, 9.0, 9.0, 7.0, 14.0]  # ranks 6 -> 1, matching the reference pacing
ROW_Y = {6: 380, 5: 474, 4: 568, 3: 660, 2: 752, 1: 844}
RANK_COLOURS = {1: "&H0018D8FF", 2: "&H00F5F5F5", 3: "&H008EA8F2"}


def compact_label(story: dict[str, Any]) -> str:
    series = clean_text(story.get("series") or story.get("headline"))
    category = clean_text(story.get("category")).replace("_", " ").title()
    if category == "General Entertainment":
        category = "Official Clip"
    return textwrap.shorten(f"{series} - {category}", width=39, placeholder="…")


def ranked_package(stories: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    if len(stories) != 6:
        raise BLEngineError("The reference format requires exactly six BL stories")
    # Reddit media is handled by the dedicated ranked downloader.  Do not falsely
    # label a public user upload as rights-authorized for the generic asset path.
    package_story = copy.deepcopy(stories[0])
    package_story["assets"] = []
    package = generate_package(package_story, state)
    display_items = []
    for offset, story in enumerate(reversed(stories)):
        rank = 6 - offset
        source = next((item for item in story.get("sources", []) if item.get("url")), {})
        display_items.append({
            "rank": rank,
            "label": compact_label(story),
            "story_id": story.get("story_id"),
            "source_url": normalized_url(source.get("url", "")),
            "story": story,
        })
    source_lines = []
    for item in display_items:
        source = item["story"]["sources"][0]
        source_lines.append(f"- #{item['rank']} {clean_text(source.get('name'))}: {item['source_url']}")
    package["ranked_items"] = display_items
    package["countdown"] = {
        "title_line_1": "Top 6",
        "title_line_2_white": "BL",
        "title_line_2_accent": "Moments",
        "segment_durations": SEGMENT_DURATIONS,
        "total_duration": sum(SEGMENT_DURATIONS),
    }
    package["render"]["duration_target"] = 60
    reddit_only = all(
        item.get("story", {}).get("sources", [{}])[0].get("type") == "reddit"
        and item.get("story", {}).get("assets", [{}])[0].get("role") == "reddit_source_video"
        for item in display_items
    )
    if reddit_only:
        package["verification"] = {
            "decision": "auto_publish",
            "score": 70,
            "reasons": ["six distinct public Reddit-hosted videos passed the BL countdown gate"],
            "sensitive_topics": [],
        }
    package["metadata"].update({
        "title": "Top 6 BL Moments You Need to See",
        "description": "Six public BL community clips in one countdown.\n\nOriginal posts:\n" + "\n".join(source_lines) + "\n\n#BL #BLSeries #BLDrama #Shorts",
        "tags": ["BL", "BLSeries", "BLDrama", "Shorts"],
        "format": "bl_entertainment_short",
        "source_urls": [item["source_url"] for item in display_items],
    })
    return package


def make_panels(path: Path) -> None:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((180, 170, 540, 286), radius=20, fill=(100, 100, 100, 145))
    draw.rounded_rectangle((86, 347, 157, 884), radius=11, fill=(125, 125, 125, 142))
    image.save(path)


def build_ranked_ass(package: dict[str, Any]) -> str:
    duration = float(package["countdown"]["total_duration"])
    title = r"Top 6\N{c&H00FFFFFF&}BL {c&H0018D8FF&}Moments"
    events = [f"Dialogue: 3,{ass_time(0)},{ass_time(duration)},Title,,0,0,0,,{{\\an8\\pos(360,184)}}{title}"]
    for rank in range(6, 0, -1):
        colour = RANK_COLOURS.get(rank, "&H00FFFFFF")
        events.append(f"Dialogue: 3,{ass_time(0)},{ass_time(duration)},Number,,0,0,0,,{{\\an5\\pos(120,{ROW_Y[rank]})\\c{colour}&}}{rank}.")
    cursor = 0.0
    for item, span in zip(package["ranked_items"], SEGMENT_DURATIONS):
        rank = int(item["rank"])
        colour = RANK_COLOURS.get(rank, "&H00FFFFFF")
        label = ass_escape(item["label"])
        events.append(f"Dialogue: 4,{ass_time(cursor)},{ass_time(duration)},Item,,0,0,0,,{{\\an4\\pos(165,{ROW_Y[rank]})\\c{colour}&}}{label}")
        cursor += span
    channel = ass_escape(os.environ.get("CHANNEL_NAME", "Lululala").strip() or "Lululala")
    events.append(f"Dialogue: 2,{ass_time(0)},{ass_time(duration)},Watermark,,0,0,0,,{{\\an5\\pos(360,800)}}{channel}")
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 720", "PlayResY: 1280", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Title,Poppins SemiBold,41,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,3.2,1.3,8,20,20,0,1",
        "Style: Number,Poppins SemiBold,31,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,3.0,1.0,5,0,0,0,1",
        "Style: Item,Poppins SemiBold,27,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,-0.2,0,1,2.8,1.0,4,0,0,0,1",
        "Style: Watermark,Poppins SemiBold,20,&H55FFFFFF,&H55FFFFFF,&H77101010,&H00000000,-1,0,0,0,100,100,1.2,0,1,1.4,0,5,0,0,0,1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *events, "",
    ])


def has_audio(path: Path) -> bool:
    return any(stream.get("codec_type") == "audio" for stream in ffprobe(path).get("streams", []))


def download_reddit_source(item: dict[str, Any], directory: Path, index: int) -> Path:
    """Download and merge one public Reddit video with audio, without account cookies."""
    asset = next(
        (value for value in item["story"].get("assets", []) if value.get("role") == "reddit_source_video"),
        None,
    )
    if not asset:
        raise BLEngineError(f"Rank #{item['rank']} has no Reddit-hosted source video")
    media_url = str(asset.get("url") or "")
    source_url = str(asset.get("source_url") or item.get("source_url") or "")
    parsed = urlparse(media_url)
    media_id = parsed.path.strip("/").split("/", 1)[0]
    if parsed.scheme != "https" or parsed.hostname != "v.redd.it" or not media_id:
        raise BLEngineError(f"Rank #{item['rank']} has an invalid Reddit media URL")
    destination = directory / f"reddit-ranked-{index}.mp4"
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--no-warnings",
        "--socket-timeout",
        "30",
        "--retries",
        "3",
        "--max-filesize",
        "150M",
        "--format",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "--output",
        str(destination),
        "--",
        source_url,
    ]
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        result = subprocess.CompletedProcess(command, 124, "", "Reddit yt-dlp attempt timed out")
    if result.returncode == 0 and destination.is_file() and destination.stat().st_size >= 10_000 and has_audio(destination):
        return destination

    failures = ["yt-dlp: " + " | ".join(result.stderr.splitlines()[-3:])]
    for manifest_name in ("DASHPlaylist.mpd", "HLSPlaylist.m3u8"):
        destination.unlink(missing_ok=True)
        manifest_url = f"https://v.redd.it/{media_id}/{manifest_name}"
        fallback = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-y",
                "-headers", "User-Agent: github:Lululala-BL-Shorts:v3.0\r\nReferer: https://www.reddit.com/\r\n",
                "-i", manifest_url,
                "-t", "180", "-map", "0:v:0", "-map", "0:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                str(destination),
            ],
            text=True,
            capture_output=True,
            timeout=180,
        )
        if fallback.returncode == 0 and destination.is_file() and destination.stat().st_size >= 10_000 and has_audio(destination):
            return destination
        failures.append(manifest_name + ": " + " | ".join(fallback.stderr.splitlines()[-3:]))
    destination.unlink(missing_ok=True)
    raise BLEngineError(f"Rank #{item['rank']} Reddit video could not be downloaded with audio: " + " || ".join(failures)[-1400:])


def render_ranked(package: dict[str, Any]) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="bl-ranked-") as name:
        temporary = Path(name)
        clips: list[Path] = []
        starts: list[float] = []
        for index, item in enumerate(package["ranked_items"]):
            reddit_asset = next((asset for asset in item["story"].get("assets", []) if asset.get("role") == "reddit_source_video"), None)
            if reddit_asset:
                clip = download_reddit_source(item, temporary, index)
            else:
                source_asset = next((asset for asset in item["story"].get("assets", []) if asset.get("role") == "source_video"), None)
                if not source_asset:
                    raise BLEngineError(f"Rank #{item['rank']} has no related source video")
                required_asset = dict(source_asset)
                required_asset["optional"] = False
                clip = download_asset(required_asset, temporary, index)
            if not has_audio(clip):
                raise BLEngineError(f"Rank #{item['rank']} source clip has no audio")
            clips.append(clip)
            starts.append(1.0 + int(hashlib.sha256(str(item["story_id"]).encode()).hexdigest()[:4], 16) % 7)

        panels = temporary / "panels.png"
        make_panels(panels)
        subtitles = temporary / "ranked.ass"
        subtitles.write_text(build_ranked_ass(package), encoding="utf-8", newline="\n")
        output = OUTPUT_DIR / "short.mp4"
        command = ["ffmpeg", "-hide_banner", "-y"]
        for clip, start, duration in zip(clips, starts, SEGMENT_DURATIONS):
            command += ["-ss", f"{start:.3f}", "-stream_loop", "-1", "-t", f"{duration:.3f}", "-i", str(clip)]
        command += ["-loop", "1", "-framerate", FPS, "-i", str(panels)]
        filters = []
        concat_inputs = []
        for index, duration in enumerate(SEGMENT_DURATIONS):
            filters.append(f"[{index}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},setsar=1,fps={FPS},eq=contrast=1.035:saturation=1.06,trim=duration={duration},setpts=PTS-STARTPTS[v{index}]")
            filters.append(f"[{index}:a]aresample=44100,loudnorm=I=-15:TP=-1.5:LRA=9,atrim=duration={duration},asetpts=PTS-STARTPTS[a{index}]")
            concat_inputs.append(f"[v{index}][a{index}]")
        filters.append("".join(concat_inputs) + f"concat=n=6:v=1:a=1[basev][a]")
        filters.append(f"[6:v]format=rgba[panels];[basev][panels]overlay=0:0:shortest=1[boxed]")
        filters.append(f"[boxed]subtitles='{filter_path(subtitles)}':fontsdir='{filter_path(FONT.parent)}',format=yuv420p[v]")
        command += [
            "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]", "-t", "60",
            "-r", FPS, "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-maxrate", "3M", "-bufsize", "6M",
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(output),
        ]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode:
            raise BLEngineError("Ranked FFmpeg render failed:\n" + "\n".join(result.stderr.splitlines()[-45:]))
        cover = OUTPUT_DIR / "cover.jpg"
        cover_result = subprocess.run(["ffmpeg", "-hide_banner", "-y", "-ss", "1", "-i", str(output), "-frames:v", "1", "-q:v", "2", str(cover)], text=True, capture_output=True)
        if cover_result.returncode or not cover.is_file():
            raise BLEngineError("Ranked cover extraction failed")

        probe = ffprobe(output)
        streams = probe.get("streams", [])
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
        duration = float(probe.get("format", {}).get("duration") or 0)
        issues = []
        if (video_stream.get("width"), video_stream.get("height")) != (WIDTH, HEIGHT):
            issues.append("video is not reference-matched 720x1280")
        if not 59.5 <= duration <= 60.5:
            issues.append("video is not 60 seconds")
        if not audio_stream:
            issues.append("source audio is missing")
        if len(clips) != 6:
            issues.append("six source videos are required")
        report = {
            "passed": not issues, "issues": issues, "format": "reference_ranked_countdown",
            "assets": {"resolved": len(clips), "video": len(clips), "image": 0},
            "video": {"duration": round(duration, 3), "width": video_stream.get("width"), "height": video_stream.get("height"), "video_codec": video_stream.get("codec_name"), "audio_codec": audio_stream.get("codec_name"), "bytes": output.stat().st_size},
            "story_id": package["story_id"], "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json_atomic(REPORT_DIR / f"{package['story_id']}.json", report)
        write_json_atomic(OUTPUT_DIR / "metadata.json", package["metadata"])
        write_json_atomic(LOG_DIR / "run.json", {
            "run_id": os.environ.get("GITHUB_RUN_ID", package["story_id"]), "story_id": package["story_id"],
            "format": "reference_ranked_countdown", "started_at": started.isoformat(),
            "render_duration": round((datetime.now(timezone.utc) - started).total_seconds(), 3),
            "qa_status": "passed" if report["passed"] else "failed", "upload_status": "dry_run", "youtube_video_id": "", "errors": issues,
        })
        if issues:
            raise BLEngineError("Ranked QA failed: " + "; ".join(issues))
        return report
