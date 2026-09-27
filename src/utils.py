from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


_PROBE_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}


def run(command: list[str], *, cwd: Path | None = None, check: bool = True,
        timeout: float = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=check, capture_output=True, text=True,
                          timeout=timeout)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ffprobe(path: Path, binary: str | None = None) -> dict[str, Any]:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    fallback = Path(__file__).resolve().parents[1] / ".test-tools" / "ffprobe.exe"
    executable = binary or os.getenv("FFPROBE_BIN") or shutil.which("ffprobe")
    if not executable and fallback.is_file():
        executable = str(fallback)
    if executable:
        result = run([executable, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
        payload = json.loads(result.stdout)
    else:
        # A full FFmpeg install normally includes ffprobe. This parser is a
        # portable fallback for local dry-runs where an application bundles
        # only ffmpeg.exe; production GitHub runners still use ffprobe JSON.
        ffmpeg = os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffprobe or ffmpeg is required")
        result = run([ffmpeg, "-hide_banner", "-i", str(path)], check=False, timeout=90)
        details = result.stderr
        duration_match = re.search(r"Duration:\s*(\d+):(\d+):([0-9.]+)", details)
        duration = 0.0
        if duration_match:
            duration = int(duration_match.group(1)) * 3600 + int(duration_match.group(2)) * 60 + float(duration_match.group(3))
        streams: list[dict[str, Any]] = []
        video_match = re.search(r"Video:\s*([\w]+).*?(\d{2,5})x(\d{2,5}).*?([0-9.]+)\s*fps", details)
        if video_match:
            fps = float(video_match.group(4))
            streams.append({"codec_type": "video", "codec_name": video_match.group(1),
                            "width": int(video_match.group(2)), "height": int(video_match.group(3)),
                            "avg_frame_rate": f"{round(fps * 1000)}/1000", "duration": str(duration)})
        audio_match = re.search(r"Audio:\s*([\w]+)", details)
        if audio_match:
            streams.append({"codec_type": "audio", "codec_name": audio_match.group(1), "duration": str(duration)})
        if duration <= 0 or not streams:
            raise RuntimeError("ffmpeg could not inspect media")
        payload = {"format": {"duration": str(duration)}, "streams": streams}
    _PROBE_CACHE[key] = payload
    return payload


def safe_filename(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "-_" else "-" for character in value)
    return cleaned.strip("-")[:80] or "asset"
