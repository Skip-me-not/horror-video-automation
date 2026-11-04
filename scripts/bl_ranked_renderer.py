#!/usr/bin/env python3
"""Render a retention-first K-pop countdown with a cold-open payoff teaser."""

from __future__ import annotations

import copy
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageDraw

from scripts.bl_engine import BLEngineError, ROOT, clean_text, generate_package, normalized_url, write_json_atomic
from scripts.bl_renderer import FONT, LOG_DIR, OUTPUT_DIR, REPORT_DIR, ass_escape, ass_time, download_asset, ffprobe, filter_path

WIDTH, HEIGHT = 720, 1280
FPS = "30000/1001"
HOOK_DURATION = 1.8
SEGMENT_DURATIONS = [4.4, 4.4, 4.8, 5.2, 6.2, 8.2]  # ranks 6 -> 1
TOTAL_DURATION = round(HOOK_DURATION + sum(SEGMENT_DURATIONS), 3)
RANK_COLOURS = {1: "&H0018D8FF", 2: "&H00F5F5F5", 3: "&H008EA8F2"}

LABEL_RULES = (
    (("dance", "choreo", "challenge"), "THE DANCE MOMENT"),
    (("vocal", "sing", "voice", "note"), "VOCALS WENT OFF"),
    (("stage", "performance", "concert", "fancam"), "THE STAGE MOMENT"),
    (("crowd", "audience", "cheer"), "THE CROWD REACTION"),
    (("funny", "laugh", "chaos", "meme"), "PURE CHAOS"),
    (("fashion", "shoot", "vogue", "calvin", "prada", "look"), "THE ICONIC LOOK"),
    (("live", "stream"), "THE LIVE MOMENT"),
    (("award", "win", "record", "first"), "THE MILESTONE"),
)


def compact_label(story: dict[str, Any], topic: str = "") -> str:
    series = clean_text(story.get("series") or story.get("headline"))
    series = re.sub(r"^\s*\d{6,8}\s*[-_:]?\s*", "", series).strip()
    lowered = series.casefold()
    for terms, label in LABEL_RULES:
        if any(term in lowered for term in terms):
            return label
    series = re.sub(r"(?i)\b(?:instagram|twitter|youtube|tiktok|weverse)\s+(?:story\s+)?update\b", "", series)
    if topic:
        series = re.sub(rf"(?i)\b{re.escape(topic)}\b", "", series)
    series = re.sub(r"[#@][A-Za-z0-9_]+|[^A-Za-z0-9'& -]", " ", series)
    series = re.sub(r"\s+", " ", series).strip(" -_:|'")
    words = series.split()
    if len(words) > 5:
        words = words[-5:]
    return (" ".join(words) or "FAN-FAVORITE MOMENT").upper()


def fan_score(value: Any) -> str:
    score = max(0, int(value or 0))
    if score >= 1_000_000:
        return f"{score / 1_000_000:.1f}M"
    if score >= 1000:
        return f"{score / 1000:.1f}K"
    return str(score)


def ranked_package(stories: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    if len(stories) != 6:
        raise BLEngineError("The reference format requires exactly six K-pop stories")
    # Reddit media is handled by the dedicated ranked downloader.  Do not falsely
    # label a public user upload as rights-authorized for the generic asset path.
    package_story = copy.deepcopy(stories[0])
    package_story["assets"] = []
    package = generate_package(package_story, state)
    topic = clean_text(stories[0].get("ranked_topic") or "K-pop")
    display_items = []
    seen_labels: dict[str, int] = {}
    for offset, story in enumerate(reversed(stories)):
        rank = 6 - offset
        source = next((item for item in story.get("sources", []) if item.get("url")), {})
        label = compact_label(story, topic)
        seen_labels[label] = seen_labels.get(label, 0) + 1
        if seen_labels[label] > 1:
            label = f"{label} #{seen_labels[label]}"
        display_items.append({
            "rank": rank,
            "label": label,
            "fan_score": fan_score(story.get("reddit_score")),
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
        "title_line_2_white": topic,
        "title_line_2_accent": "Moments",
        "hook_line": "WAIT FOR #1",
        "hook_subline": f"FANS RANKED THESE {topic.upper()} MOMENTS",
        "hook_duration": HOOK_DURATION,
        "segment_durations": SEGMENT_DURATIONS,
        "total_duration": TOTAL_DURATION,
    }
    package["render"]["duration_target"] = TOTAL_DURATION
    reddit_only = all(
        item.get("story", {}).get("sources", [{}])[0].get("type") == "reddit"
        and item.get("story", {}).get("assets", [{}])[0].get("role") == "reddit_source_video"
        for item in display_items
    )
    if reddit_only:
        package["verification"] = {
            "decision": "auto_publish",
            "score": 70,
            "reasons": ["six distinct public Reddit-hosted videos passed the K-pop countdown gate"],
            "sensitive_topics": [],
        }
    package["metadata"].update({
        "title": f"6 {topic} Moments Fans Ranked Highest",
        "description": f"Six {topic} K-pop moments ranked by Reddit fan upvotes.\n\nOriginal posts:\n" + "\n".join(source_lines) + f"\n\n#Kpop #{re.sub(r'[^A-Za-z0-9]', '', topic)} #KpopShorts #Shorts",
        "tags": ["Kpop", topic, "KpopShorts", "Shorts"],
        "format": "kpop_entertainment_short",
        "source_urls": [item["source_url"] for item in display_items],
    })
    return package


def make_panels(path: Path) -> None:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((42, 105, 678, 342), radius=22, fill=(32, 32, 32, 146))
    image.save(path)


def build_ranked_ass(package: dict[str, Any]) -> str:
    duration = float(package["countdown"]["total_duration"])
    topic = ass_escape(clean_text(package["countdown"].get("title_line_2_white") or "K-POP"))
    hook_duration = float(package["countdown"].get("hook_duration") or HOOK_DURATION)
    hook = ass_escape(clean_text(package["countdown"].get("hook_line") or "WAIT FOR #1"))
    hook_subline = ass_escape(clean_text(package["countdown"].get("hook_subline") or "FANS RANKED THESE MOMENTS"))
    title = rf"TOP 6 {{\c&H00FFFFFF&}}{topic.upper()} {{\c&H0018D8FF&}}MOMENTS"
    events = [
        f"Dialogue: 5,{ass_time(0)},{ass_time(hook_duration)},Hook,,0,0,0,,{{\\an5\\pos(360,490)}}{hook}",
        f"Dialogue: 5,{ass_time(0.18)},{ass_time(hook_duration)},HookSub,,0,0,0,,{{\\an5\\pos(360,565)}}{hook_subline}",
        f"Dialogue: 3,{ass_time(hook_duration)},{ass_time(duration)},Title,,0,0,0,,{{\\an8\\pos(360,126)}}{title}",
    ]
    cursor = hook_duration
    for item, span in zip(package["ranked_items"], SEGMENT_DURATIONS):
        rank = int(item["rank"])
        colour = RANK_COLOURS.get(rank, "&H00FFFFFF")
        label = ass_escape(item["label"])
        end = cursor + span
        events.append(f"Dialogue: 4,{ass_time(cursor)},{ass_time(end)},Rank,,0,0,0,,{{\\an5\\pos(105,225)\\c{colour}&}}#{rank}")
        events.append(f"Dialogue: 4,{ass_time(cursor)},{ass_time(end)},Item,,0,0,0,,{{\\an4\\pos(170,222)\\c{colour}&}}{label}")
        events.append(f"Dialogue: 4,{ass_time(cursor + 0.18)},{ass_time(end)},Context,,0,0,0,,{{\\an4\\pos(170,292)}}RANKED BY {item['fan_score']} FAN UPVOTES")
        cursor += span
    final_start = duration - SEGMENT_DURATIONS[-1] + 4.8
    events.append(f"Dialogue: 4,{ass_time(final_start)},{ass_time(duration)},CTA,,0,0,0,,{{\\an2\\pos(360,1115)}}WHO SHOULD WE RANK NEXT?")
    channel = ass_escape(os.environ.get("CHANNEL_NAME", "Lululala").strip() or "Lululala")
    events.append(f"Dialogue: 2,{ass_time(0)},{ass_time(duration)},Watermark,,0,0,0,,{{\\an2\\pos(360,1215)}}{channel}")
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 720", "PlayResY: 1280", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Title,Poppins SemiBold,31,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,2.8,1.1,8,20,20,0,1",
        "Style: Hook,Poppins SemiBold,56,&H0018D8FF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,4.0,1.5,5,20,20,0,1",
        "Style: HookSub,Poppins SemiBold,23,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0.6,0,1,2.6,1.0,5,20,20,0,1",
        "Style: Rank,Poppins SemiBold,39,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,3.0,1.0,5,0,0,0,1",
        "Style: Item,Poppins SemiBold,29,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,-0.2,0,1,2.8,1.0,4,0,0,0,1",
        "Style: Context,Poppins SemiBold,18,&H00E8E8E8,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0.8,0,1,2.2,0.8,4,0,0,0,1",
        "Style: CTA,Poppins SemiBold,24,&H0018D8FF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0.5,0,1,3.0,1.0,2,20,20,0,1",
        "Style: Watermark,Poppins SemiBold,17,&H55FFFFFF,&H55FFFFFF,&H77101010,&H00000000,-1,0,0,0,100,100,1.2,0,1,1.4,0,2,0,0,0,1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *events, "",
    ])


def has_audio(path: Path) -> bool:
    return any(stream.get("codec_type") == "audio" for stream in ffprobe(path).get("streams", []))


def media_duration(path: Path) -> float:
    try:
        return float(ffprobe(path).get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        return 0.0


def highlight_start(path: Path, span: float) -> float:
    """Choose an early scene change instead of a random timestamp."""
    duration = media_duration(path)
    max_start = max(0.0, duration - span - 0.15)
    if max_start <= 0.2:
        return 0.0
    scan_seconds = min(duration, 18.0)
    command = [
        "ffmpeg", "-hide_banner", "-i", str(path), "-t", f"{scan_seconds:.3f}",
        "-vf", "select='gt(scene,0.22)',showinfo", "-an", "-f", "null", "-",
    ]
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=45)
    except subprocess.TimeoutExpired:
        return round(min(0.35, max_start), 3)
    candidates = [
        float(value)
        for value in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", result.stderr)
        if 0.35 <= float(value) <= max_start
    ]
    return round(candidates[0] if candidates else min(0.35, max_start), 3)


def black_durations(path: Path) -> list[float]:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path),
            "-vf", "blackdetect=d=0.8:pix_th=0.10", "-an", "-f", "null", "-",
        ],
        text=True,
        capture_output=True,
        timeout=90,
    )
    return [float(value) for value in re.findall(r"black_duration:([0-9]+(?:\.[0-9]+)?)", result.stderr)]


def download_reddit_source(item: dict[str, Any], directory: Path, index: int) -> Path:
    """Download and merge one public Reddit video with audio, without account cookies."""
    asset = next(
        (value for value in item["story"].get("assets", []) if value.get("role") == "reddit_source_video"),
        None,
    )
    if not asset:
        raise BLEngineError(f"Rank #{item['rank']} has no Reddit-hosted source video")
    media_url = str(asset.get("url") or "")
    parsed = urlparse(media_url)
    media_id = parsed.path.strip("/").split("/", 1)[0]
    if parsed.scheme != "https" or parsed.hostname != "v.redd.it" or not media_id:
        raise BLEngineError(f"Rank #{item['rank']} has an invalid Reddit media URL")
    destination = directory / f"reddit-ranked-{index}.mp4"
    failures: list[str] = []
    for manifest_name in ("HLSPlaylist.m3u8", "DASHPlaylist.mpd"):
        destination.unlink(missing_ok=True)
        manifest_url = f"https://v.redd.it/{media_id}/{manifest_name}"
        command = [
            "ffmpeg", "-hide_banner", "-y",
            "-headers", "User-Agent: github:Lululala-Kpop-Shorts:v4.0\r\nReferer: https://www.reddit.com/\r\n",
            "-i", manifest_url,
            "-t", "180", "-map", "0:v:0", "-map", "0:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            str(destination),
        ]
        try:
            fallback = subprocess.run(command, text=True, capture_output=True, timeout=180)
        except subprocess.TimeoutExpired:
            fallback = subprocess.CompletedProcess(command, 124, "", f"{manifest_name} timed out")
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
            starts.append(highlight_start(clip, SEGMENT_DURATIONS[index]))

        panels = temporary / "panels.png"
        make_panels(panels)
        subtitles = temporary / "ranked.ass"
        subtitles.write_text(build_ranked_ass(package), encoding="utf-8", newline="\n")
        output = OUTPUT_DIR / "short.mp4"
        command = ["ffmpeg", "-hide_banner", "-y"]
        rank_one_duration = media_duration(clips[-1])
        teaser_start = min(starts[-1] + 2.0, max(0.0, rank_one_duration - HOOK_DURATION - 0.15))
        command += ["-ss", f"{teaser_start:.3f}", "-stream_loop", "-1", "-t", f"{HOOK_DURATION:.3f}", "-i", str(clips[-1])]
        for clip, start, duration in zip(clips, starts, SEGMENT_DURATIONS):
            command += ["-ss", f"{start:.3f}", "-stream_loop", "-1", "-t", f"{duration:.3f}", "-i", str(clip)]
        command += ["-loop", "1", "-framerate", FPS, "-i", str(panels)]
        filters = []
        concat_inputs = []
        all_durations = [HOOK_DURATION, *SEGMENT_DURATIONS]
        for index, duration in enumerate(all_durations):
            filters.append(f"[{index}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},setsar=1,fps={FPS},eq=contrast=1.035:saturation=1.06,trim=duration={duration},setpts=PTS-STARTPTS[v{index}]")
            fade_out = max(0.0, duration - 0.10)
            filters.append(f"[{index}:a]aresample=44100,loudnorm=I=-15:TP=-1.5:LRA=9,atrim=duration={duration},afade=t=in:st=0:d=0.06,afade=t=out:st={fade_out:.3f}:d=0.10,asetpts=PTS-STARTPTS[a{index}]")
            concat_inputs.append(f"[v{index}][a{index}]")
        filters.append("".join(concat_inputs) + f"concat=n=7:v=1:a=1[basev][a]")
        filters.append(f"[7:v]format=rgba[panels];[basev][panels]overlay=0:0:shortest=1:enable='gte(t,{HOOK_DURATION})'[boxed]")
        filters.append(f"[boxed]subtitles='{filter_path(subtitles)}':fontsdir='{filter_path(FONT.parent)}',format=yuv420p[v]")
        command += [
            "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]", "-t", f"{TOTAL_DURATION:.3f}",
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
        if not TOTAL_DURATION - 0.5 <= duration <= TOTAL_DURATION + 0.5:
            issues.append(f"video is not {TOTAL_DURATION:.1f} seconds")
        if not audio_stream:
            issues.append("source audio is missing")
        if len(clips) != 6:
            issues.append("six source videos are required")
        dark_spans = black_durations(output)
        if dark_spans and max(dark_spans) > 1.0:
            issues.append(f"black screen lasts {max(dark_spans):.2f} seconds")
        report = {
            "passed": not issues, "issues": issues, "format": "retention_ranked_countdown_v2",
            "assets": {"resolved": len(clips), "video": len(clips), "image": 0},
            "video": {"duration": round(duration, 3), "width": video_stream.get("width"), "height": video_stream.get("height"), "video_codec": video_stream.get("codec_name"), "audio_codec": audio_stream.get("codec_name"), "bytes": output.stat().st_size},
            "story_id": package["story_id"], "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json_atomic(REPORT_DIR / f"{package['story_id']}.json", report)
        write_json_atomic(OUTPUT_DIR / "metadata.json", package["metadata"])
        write_json_atomic(LOG_DIR / "run.json", {
            "run_id": os.environ.get("GITHUB_RUN_ID", package["story_id"]), "story_id": package["story_id"],
            "format": "retention_ranked_countdown_v2", "started_at": started.isoformat(),
            "render_duration": round((datetime.now(timezone.utc) - started).total_seconds(), 3),
            "qa_status": "passed" if report["passed"] else "failed", "upload_status": "dry_run", "youtube_video_id": "", "errors": issues,
        })
        if issues:
            raise BLEngineError("Ranked QA failed: " + "; ".join(issues))
        return report
