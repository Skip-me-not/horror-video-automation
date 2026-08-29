from __future__ import annotations

import json
import os
import shutil
import subprocess
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...]
    probe: dict[str, Any]


def validate_video(path: Path, width: int = 1080, height: int = 1920,
                   minimum: float = 15.0, maximum: float = 30.0,
                   ffprobe: str | None = None) -> ValidationResult:
    errors: list[str] = []
    if not path.is_file() or path.stat().st_size < 100_000:
        return ValidationResult(False, ("video is missing or below 100 KB",), {})
    fallback = Path(__file__).resolve().parents[1] / ".test-tools" / "ffprobe.exe"
    probe_binary = ffprobe or os.getenv("FFPROBE_BIN") or shutil.which("ffprobe")
    if not probe_binary and fallback.is_file():
        probe_binary = str(fallback)
    command = [probe_binary or "ffprobe", "-v", "error", "-show_streams",
               "-show_format", "-of", "json", str(path)]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        probe = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        return ValidationResult(False, (f"ffprobe failed: {exc}",), {})
    streams = probe.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    duration = float(probe.get("format", {}).get("duration", 0.0))
    if (int(video.get("width", 0)), int(video.get("height", 0))) != (width, height):
        errors.append(f"video must be {width}x{height}")
    if video.get("codec_name") != "h264":
        errors.append("video codec must be H.264")
    if not audio:
        errors.append("AAC audio stream is required")
    elif audio.get("codec_name") != "aac":
        errors.append("audio codec must be AAC")
    if not minimum <= duration <= maximum:
        errors.append(f"duration {duration:.2f}s is outside {minimum:.0f}-{maximum:.0f}s")
    frame_rate = str(video.get("avg_frame_rate", "0/1")).split("/")
    try:
        fps = float(frame_rate[0]) / float(frame_rate[1])
        if abs(fps - 30.0) > 0.1:
            errors.append(f"frame rate must be 30 FPS, got {fps:.2f}")
    except (ValueError, ZeroDivisionError, IndexError):
        errors.append("frame rate could not be read")
    return ValidationResult(not errors, tuple(errors), probe)


def validate_story_short(path: Path, minimum: float = 60.0, maximum: float = 180.0,
                         ffprobe: str | None = None) -> ValidationResult:
    result = validate_video(path, 1080, 1920, minimum, maximum, ffprobe)
    errors = list(result.errors)
    streams = result.probe.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    try:
        video_duration = float(video.get("duration") or result.probe.get("format", {}).get("duration") or 0)
        audio_duration = float(audio.get("duration") or result.probe.get("format", {}).get("duration") or 0)
        if abs(video_duration - audio_duration) > 0.35:
            errors.append("audio/video durations differ by more than 0.35 seconds")
    except (TypeError, ValueError):
        errors.append("audio/video duration could not be verified")
    if path.is_file() and path.stat().st_size < 500_000:
        errors.append("final file is suspiciously small")
    ffmpeg_binary = shutil.which("ffmpeg")
    if ffmpeg_binary and path.is_file():
        black_check = subprocess.run(
            [ffmpeg_binary, "-hide_banner", "-i", str(path), "-vf",
             "blackdetect=d=0.5:pix_th=0.02", "-an", "-f", "null", "-"],
            capture_output=True, text=True, check=False,
        )
        black_durations = [float(value) for value in
                           re.findall(r"black_duration:([0-9.]+)", black_check.stderr)]
        if any(duration >= 0.5 for duration in black_durations):
            errors.append(f"black screen detected ({max(black_durations):.2f}s)")
    return ValidationResult(not errors, tuple(errors), result.probe)
