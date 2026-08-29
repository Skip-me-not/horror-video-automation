from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config_loader import Settings


def download_source(url: str, destination: Path, settings: Settings) -> dict[str, Any]:
    import yt_dlp
    destination.mkdir(parents=True, exist_ok=True)
    template = str(destination / "source.%(ext)s")
    options = {
        "format": f"bestvideo[height<={settings.download_max_height}]+bestaudio/best[height<={settings.download_max_height}]",
        "outtmpl": template,
        "merge_output_format": "mp4",
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB"],
        "subtitlesformat": "vtt",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
    video_candidates = sorted(destination.glob("source.*"))
    video = next((path for path in video_candidates if path.suffix.casefold() in {".mp4", ".mkv", ".webm", ".mov"}), None)
    if video is None or video.stat().st_size == 0:
        raise RuntimeError("source download produced no playable media")
    subtitles = next(iter(sorted(destination.glob("source*.vtt"))), None)
    return {"video": video, "subtitles": subtitles, "info": info}


def use_local_source(source: Path, destination: Path) -> dict[str, Any]:
    if not source.is_file() or source.stat().st_size == 0:
        raise FileNotFoundError(source)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"source{source.suffix.casefold()}"
    shutil.copy2(source, target)
    sidecar = source.with_suffix(".vtt")
    subtitle_target = None
    if sidecar.is_file():
        subtitle_target = destination / "source.en.vtt"
        shutil.copy2(sidecar, subtitle_target)
    return {"video": target, "subtitles": subtitle_target,
            "info": {"id": source.stem, "title": source.stem, "webpage_url": str(source),
                     "channel": "local authorized source", "channel_id": "local", "duration": None}}
