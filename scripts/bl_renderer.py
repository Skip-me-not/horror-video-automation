#!/usr/bin/env python3
"""Reusable FFmpeg renderer and deterministic QA for BL entertainment Shorts."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from scripts.bl_engine import BLEngineError, CONFIG_PATH, ROOT, read_json, write_json_atomic

OUTPUT_DIR = ROOT / "output"
LOG_DIR = ROOT / "logs"
REPORT_DIR = ROOT / "quality_reports"
FONT = ROOT / "assets" / "fonts" / "Poppins-SemiBold.ttf"
MUSIC_DIR = ROOT / "music"


def ffprobe(path: Path) -> dict[str, Any]:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], text=True, capture_output=True)
    if result.returncode:
        raise BLEngineError(f"ffprobe failed for {path.name}: {result.stderr[-600:]}")
    return json.loads(result.stdout)


def media_kind(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return "image"
    streams = ffprobe(path).get("streams", [])
    return "video" if any(item.get("codec_type") == "video" for item in streams) else "unknown"


def download_asset(asset: dict[str, Any], directory: Path, index: int) -> Path:
    if not asset.get("authorized"):
        raise BLEngineError("Renderer refused an asset not explicitly marked authorized")
    raw_path = str(asset.get("path") or "").strip()
    if raw_path:
        source = (ROOT / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path).resolve()
        if ROOT.resolve() not in source.parents and source != ROOT.resolve():
            raise BLEngineError("Asset paths must stay inside the repository")
        if not source.is_file() or source.stat().st_size == 0:
            raise BLEngineError(f"Missing or empty asset: {raw_path}")
        return source
    url = str(asset.get("url") or "").strip()
    if not url.startswith("https://"):
        raise BLEngineError("Remote assets must use HTTPS")
    suffix = Path(url.split("?", 1)[0]).suffix.casefold()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v"}:
        suffix = ".bin"
    destination = directory / f"asset-{index}{suffix}"
    with requests.get(url, stream=True, timeout=(10, 45), headers={"User-Agent": "Lululala-BL-News-Automation/2.0"}) as response:
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").casefold()
        if suffix == ".bin":
            suffix = ".mp4" if "video" in content_type else ".jpg"
            destination = destination.with_suffix(suffix)
        total = 0
        with destination.open("wb") as handle:
            for chunk in response.iter_content(1024 * 256):
                total += len(chunk)
                if total > 150 * 1024 * 1024:
                    raise BLEngineError("Remote asset exceeds 150 MB")
                handle.write(chunk)
    if destination.stat().st_size == 0:
        raise BLEngineError("Downloaded asset is empty")
    return destination


def ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    return f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02d}:{centiseconds // 100 % 60:02d}.{centiseconds % 100:02d}"


def ass_escape(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def build_ass(package: dict[str, Any], duration: float, channel_name: str) -> str:
    profile = package["render"]["caption_profile"]
    captions = package["script"]["captions"]
    weights = [max(1, len(re.findall(r"\w+", caption))) for caption in captions]
    total = sum(weights)
    cursor = 0.0
    events = []
    for index, (caption, weight) in enumerate(zip(captions, weights)):
        span = duration * weight / total
        end = duration if index == len(captions) - 1 else cursor + span
        style = "Hook" if index == 0 else "Default"
        events.append(f"Dialogue: 0,{ass_time(cursor)},{ass_time(end)},{style},,0,0,0,,{ass_escape(caption)}")
        cursor = end
    font_size = int(profile["font_size"])
    alignment = int(profile["alignment"])
    margin_v = int(profile["margin_v"])
    safe_channel = ass_escape(channel_name)
    events.append(f"Dialogue: 2,{ass_time(0)},{ass_time(duration)},Watermark,,0,0,0,,{safe_channel}")
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Default,Poppins SemiBold,{font_size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H78000000,-1,0,0,0,100,100,0,0,3,3,0,{alignment},80,80,{margin_v},1",
        f"Style: Hook,Poppins SemiBold,{min(78, font_size + 10)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,3,4,0,{alignment},70,70,{margin_v},1",
        "Style: Watermark,Poppins SemiBold,30,&HAAFFFFFF,&HAAFFFFFF,&H66000000,&H00000000,-1,0,0,0,100,100,1,0,1,1,0,2,50,50,90,1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *events, "",
    ])


def build_cover_ass(package: dict[str, Any], channel_name: str) -> str:
    headline = "\n".join(__import__("textwrap").wrap(package["story"]["headline"], width=22)[:4])
    category = package["story"]["category"].replace("_", " ").upper()
    # ASS colours are BBGGRR; white text remains portable while the FFmpeg card carries the accent.
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 2", "",
        "[V4+ Styles]", "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Headline,Poppins SemiBold,82,&H00FFFFFF,&H00FFFFFF,&H00101010,&H98000000,-1,0,0,0,100,100,0,0,3,4,0,5,90,90,520,1",
        "Style: Category,Poppins SemiBold,38,&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,2,0,3,2,0,8,70,70,220,1",
        "Style: Brand,Poppins SemiBold,34,&HAAFFFFFF,&HAAFFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,1,0,1,1,0,2,60,60,100,1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 1,0:00:00.00,0:00:01.00,Category,,0,0,0,,{ass_escape(category)}",
        f"Dialogue: 1,0:00:00.00,0:00:01.00,Headline,,0,0,0,,{ass_escape(headline)}",
        f"Dialogue: 1,0:00:00.00,0:00:01.00,Brand,,0,0,0,,{ass_escape(channel_name)}", "",
    ])


def filter_path(path: Path) -> str:
    return path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")


def select_music(story_id: str) -> Path | None:
    files = sorted(path for path in MUSIC_DIR.glob("*.mp3") if path.is_file())
    if not files:
        return None
    index = int(__import__("hashlib").sha256(story_id.encode()).hexdigest()[:8], 16) % len(files)
    return files[index]


def build_command(package: dict[str, Any], assets: list[Path], captions: Path, output: Path, narration: Path | None, music: Path | None) -> list[str]:
    config = read_json(CONFIG_PATH)
    target = config["target"]
    width, height, fps = target["width"], target["height"], target["fps"]
    duration = float(package["render"]["duration_target"])
    accent = package["layout"]["accent"].lstrip("#")
    command = ["ffmpeg", "-hide_banner", "-y"]
    filters = []
    if assets:
        assets = assets[:6]
        for asset in assets:
            if media_kind(asset) == "image":
                command += ["-loop", "1", "-framerate", str(fps), "-i", str(asset)]
            else:
                command += ["-stream_loop", "-1", "-i", str(asset)]
        scene_seconds = duration / len(assets)
        transition = min(0.35, scene_seconds / 5)
        motion = package["layout"]["motion"]
        for index, _asset in enumerate(assets):
            zoom = "min(zoom+0.00035,1.10)" if (motion == "zoom_in" or index % 2 == 0) else "max(1.10-0.00035*on,1.0)"
            scene_length = scene_seconds + (transition if index < len(assets) - 1 else 0)
            filters += [
                f"[{index}:v]split=2[bg{index}][fg{index}]",
                f"[bg{index}]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},gblur=sigma=28:steps=2,eq=brightness=-0.22:saturation=0.75[blur{index}]",
                f"[fg{index}]scale={width-100}:{height-360}:force_original_aspect_ratio=decrease,zoompan=z='{zoom}':d=1:s={width}x{height}:fps={fps},format=rgba[front{index}]",
                f"[blur{index}][front{index}]overlay=(W-w)/2:(H-h)/2,drawbox=x=0:y=0:w=iw:h=150:color=0x{accent}@0.75:t=fill,trim=duration={scene_length},setpts=PTS-STARTPTS[scene{index}]",
            ]
        current = "scene0"
        for index in range(1, len(assets)):
            output_label = f"joined{index}"
            transition_name = "fade" if index % 2 else "slideleft"
            filters.append(f"[{current}][scene{index}]xfade=transition={transition_name}:duration={transition}:offset={index * scene_seconds}[{output_label}]")
            current = output_label
        video_input = current
        audio_start_index = len(assets)
    else:
        command += ["-f", "lavfi", "-i", f"color=c=0x101018:s={width}x{height}:r={fps}:d={duration}"]
        filters += [f"[0:v]drawbox=x=0:y=0:w=iw:h=170:color=0x{accent}@0.85:t=fill,drawbox=x=70:y=300:w=940:h=1100:color=0x20202a@0.75:t=fill[base]"]
        video_input = "base"
        audio_start_index = 1
    audio_labels = []
    if music:
        command += ["-stream_loop", "-1", "-i", str(music)]
        volume = float(package["render"]["music_profile"]["volume"])
        filters.append(f"[{audio_start_index}:a]volume={volume},afade=t=in:st=0:d=0.5,afade=t=out:st={max(0,duration-1.2):.3f}:d=1.2,atrim=duration={duration}[music]")
        audio_labels.append("[music]")
        audio_start_index += 1
    if narration:
        command += ["-i", str(narration)]
        filters.append(f"[{audio_start_index}:a]loudnorm=I=-16:TP=-1.5:LRA=11,atrim=duration={duration}[voice]")
        audio_labels.append("[voice]")
    if not audio_labels:
        command += ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={duration}"]
        filters.append(f"[{audio_start_index}:a]atrim=duration={duration}[silent]")
        audio_labels.append("[silent]")
    if len(audio_labels) == 1:
        filters.append(f"{audio_labels[0]}anull[a]")
    else:
        filters.append("".join(audio_labels) + f"amix=inputs={len(audio_labels)}:duration=longest:normalize=0,loudnorm=I=-14:TP=-2:LRA=7[a]")
    filters.append(f"[{video_input}]subtitles='{filter_path(captions)}':fontsdir='{filter_path(FONT.parent)}',drawbox=x=0:y=h-18:w='iw*t/{duration}':h=18:color=0x{accent}@0.95:t=fill,trim=duration={duration},fps={fps},format=yuv420p[v]")
    command += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]", "-t", str(duration), "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(output)]
    return command


def qa_report(package: dict[str, Any], video: Path, assets: list[Path], narration_required: bool, *, allow_review: bool = False) -> dict[str, Any]:
    config = read_json(CONFIG_PATH)
    issues = []
    probe = ffprobe(video) if video.is_file() else {}
    streams = probe.get("streams", [])
    video_stream = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), {})
    duration = float(probe.get("format", {}).get("duration") or 0)
    qa = config["qa"]
    if not video.is_file() or video.stat().st_size < qa["min_file_bytes"]:
        issues.append("final video missing or too small")
    if video.is_file() and video.stat().st_size > qa["max_file_mb"] * 1024 * 1024:
        issues.append("final video exceeds size limit")
    if (video_stream.get("width"), video_stream.get("height")) != (qa["allowed_width"], qa["allowed_height"]):
        issues.append("video is not 1080x1920")
    if not config["target"]["min_seconds"] - 0.5 <= duration <= config["target"]["max_seconds"] + 0.5:
        issues.append("video duration is outside configured bounds")
    if not audio_stream:
        issues.append("AAC audio stream is missing")
    if narration_required and not package["story"].get("narration_file"):
        issues.append("narration mode requires a narration file")
    if any(path.stat().st_size == 0 for path in assets):
        issues.append("zero-byte media asset")
    serialized = json.dumps({"script": package.get("script"), "metadata": package.get("metadata")}, ensure_ascii=False)
    if re.search(r"\{[a-z][a-z0-9_]*\}", serialized):
        issues.append("unresolved template variable")
    for key in ("title", "description"):
        if not str(package["metadata"].get(key, "")).strip():
            issues.append(f"metadata {key} is empty")
    if package["verification"]["decision"] != "auto_publish" and not allow_review:
        issues.append("source verification does not allow automatic publication")
    if not package["metadata"].get("source_urls"):
        issues.append("verified source URL is missing")
    return {"passed": not issues, "publish_eligible": package["verification"]["decision"] == "auto_publish", "issues": issues, "video": {"duration": round(duration, 3), "width": video_stream.get("width"), "height": video_stream.get("height"), "video_codec": video_stream.get("codec_name"), "audio_codec": audio_stream.get("codec_name"), "bytes": video.stat().st_size if video.exists() else 0}}


def render(package_path: Path, *, narration_mode: str = "auto", allow_review: bool = False) -> dict[str, Any]:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise BLEngineError("ffmpeg and ffprobe are required")
    package = read_json(package_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    channel = os.environ.get("CHANNEL_NAME", "Lululala").strip() or "Lululala"
    started = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="bl-short-") as name:
        temporary = Path(name)
        assets = [download_asset(asset, temporary, index) for index, asset in enumerate(package["story"].get("assets", []))]
        narration_value = str(package["story"].get("narration_file") or "").strip()
        narration = None
        if narration_value:
            narration = (ROOT / narration_value).resolve() if not Path(narration_value).is_absolute() else Path(narration_value).resolve()
            if ROOT.resolve() not in narration.parents or not narration.is_file():
                raise BLEngineError("Narration file must exist inside the repository")
        if narration_mode == "required" and narration is None:
            raise BLEngineError("Narration mode is required but no narration_file was supplied")
        duration = float(package["render"]["duration_target"])
        captions = temporary / "captions.ass"
        captions.write_text(build_ass(package, duration, channel), encoding="utf-8", newline="\n")
        output = OUTPUT_DIR / "short.mp4"
        music = select_music(package["story_id"])
        command = build_command(package, assets, captions, output, narration, music)
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode:
            raise BLEngineError("FFmpeg render failed:\n" + "\n".join(result.stderr.splitlines()[-35:]))
        cover = OUTPUT_DIR / "cover.jpg"
        cover_subtitles = temporary / "cover.ass"
        cover_subtitles.write_text(build_cover_ass(package, channel), encoding="utf-8", newline="\n")
        accent = package["layout"]["accent"].lstrip("#")
        cover_filter = (
            f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.52:t=fill,"
            f"drawbox=x=0:y=0:w=iw:h=180:color=0x{accent}@0.92:t=fill,"
            f"subtitles='{filter_path(cover_subtitles)}':fontsdir='{filter_path(FONT.parent)}'"
        )
        cover_result = subprocess.run(["ffmpeg", "-hide_banner", "-y", "-ss", "0.5", "-i", str(output), "-vf", cover_filter, "-frames:v", "1", "-q:v", "2", str(cover)], text=True, capture_output=True)
        if cover_result.returncode or not cover.is_file():
            raise BLEngineError("Cover-frame extraction failed")
        report = qa_report(package, output, assets, narration_mode == "required", allow_review=allow_review)
        report.update({"story_id": package["story_id"], "template_id": package["template"]["id"], "layout_id": package["layout"]["id"], "checked_at": datetime.now(timezone.utc).isoformat()})
        write_json_atomic(REPORT_DIR / f"{package['story_id']}.json", report)
        write_json_atomic(OUTPUT_DIR / "metadata.json", package["metadata"])
        log = {"run_id": os.environ.get("GITHUB_RUN_ID", package["story_id"]), "story_id": package["story_id"], "category": package["story"]["category"], "template_id": package["template"]["id"], "layout_id": package["layout"]["id"], "started_at": started.isoformat(), "render_duration": round((datetime.now(timezone.utc) - started).total_seconds(), 3), "qa_status": "passed" if report["passed"] else "failed", "upload_status": "dry_run", "youtube_video_id": "", "errors": report["issues"]}
        write_json_atomic(LOG_DIR / "run.json", log)
        if not report["passed"]:
            raise BLEngineError("QA failed: " + "; ".join(report["issues"]))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=OUTPUT_DIR / "package.json")
    parser.add_argument("--narration-mode", choices=("auto", "required", "text-only"), default="auto")
    args = parser.parse_args()
    report = render(args.package, narration_mode=args.narration_mode)
    print(f"QA PASSED: {report['story_id']} {report['video']['duration']}s 1080x1920")


if __name__ == "__main__":
    try:
        main()
    except BLEngineError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
