from __future__ import annotations

import json
import os
import subprocess
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
    command = [ffprobe or os.getenv("FFPROBE_BIN", "ffprobe"), "-v", "error", "-show_streams",
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
