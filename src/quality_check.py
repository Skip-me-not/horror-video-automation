from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QualityReport:
    valid: bool
    errors: tuple[str, ...]
    probe: dict[str, Any]


class VideoQualityChecker:
    def __init__(self, ffprobe: str | None = None) -> None:
        self.ffprobe = ffprobe or os.getenv("FFPROBE_BIN", "ffprobe")

    def check(self, video: Path, narration: Path, subtitles: Path,
              script: dict[str, object], metadata: dict[str, object]) -> QualityReport:
        errors: list[str] = []
        for label, path in (("video", video), ("narration", narration), ("subtitles", subtitles)):
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"{label} is missing or empty")
        if script.get("status") != "ready" or script.get("youtube_video_id"):
            errors.append("script has already been used")
        if not metadata.get("title") or not metadata.get("description"):
            errors.append("metadata is incomplete")
        probe: dict[str, Any] = {}
        if video.is_file() and video.stat().st_size:
            try:
                result = subprocess.run(
                    [self.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
                    check=True, capture_output=True, text=True,
                )
                probe = json.loads(result.stdout)
                streams = probe.get("streams", [])
                visual = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
                audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
                duration = float(probe.get("format", {}).get("duration", 0))
                if (int(visual.get("width", 0)), int(visual.get("height", 0))) != (1080, 1920):
                    errors.append("video must be 1080x1920")
                if audio is None:
                    errors.append("video has no audio stream")
                if not 20 <= duration <= 59:
                    errors.append(f"video duration {duration:.2f}s is outside 20-59s")
            except (OSError, subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"ffprobe failed: {exc}")
        return QualityReport(not errors, tuple(errors), probe)
