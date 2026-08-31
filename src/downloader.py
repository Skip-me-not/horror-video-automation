from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config_loader import Settings


MEDIA_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4a", ".opus", ".ogg", ".mp3"}


def _youtube_options() -> dict[str, Any]:
    """Use the CI PO-token helper first, with logged-out client fallbacks."""
    cookie_file = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
    extractor_args: dict[str, dict[str, list[str]]] = {
        "youtube": {"player_client": ["default"] if cookie_file else
                    ["mweb", "web_embedded", "default"]},
    }
    provider_home = os.getenv("YTDLP_BGUTIL_SERVER_HOME", "").strip()
    if provider_home:
        extractor_args["youtubepot-bgutilscript"] = {"server_home": [provider_home]}
    options: dict[str, Any] = {"extractor_args": extractor_args}
    if cookie_file:
        options["cookiefile"] = cookie_file
    return options


def _first_media(directory: Path, prefix: str, allowed: set[str] | None = None) -> Path | None:
    suffixes = allowed or MEDIA_SUFFIXES
    return next((path for path in sorted(directory.glob(f"{prefix}.*"))
                 if path.suffix.casefold() in suffixes and path.stat().st_size > 0), None)


def download_captions(url: str, destination: Path) -> dict[str, Any]:
    """Retrieve source metadata and English VTT without downloading audio/video."""
    import yt_dlp
    destination.mkdir(parents=True, exist_ok=True)
    options = {
        **_youtube_options(),
        "skip_download": True, "writesubtitles": True, "writeautomaticsub": True,
        "subtitleslangs": ["en.*"], "subtitlesformat": "vtt",
        "outtmpl": str(destination / "source"), "quiet": True, "no_warnings": True,
        "noplaylist": True, "retries": 2, "fragment_retries": 2, "socket_timeout": 20,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
    subtitles = next(iter(sorted(destination.glob("source*.vtt"))), None)
    return {"info": info, "subtitles": subtitles}


def download_audio(url: str, destination: Path) -> Path:
    """Download one compressed audio stream for boundary analysis."""
    import yt_dlp
    destination.mkdir(parents=True, exist_ok=True)
    options = {
        **_youtube_options(),
        "format": "bestaudio[abr<=128]/bestaudio",
        "outtmpl": str(destination / "source_audio.%(ext)s"),
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "retries": 2, "fragment_retries": 2, "socket_timeout": 20,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.extract_info(url, download=True)
    audio = _first_media(destination, "source_audio")
    if audio is None:
        raise RuntimeError("audio-only download produced no playable stream")
    return audio


def download_selected_video(url: str, destination: Path, start: float, end: float,
                            settings: Settings) -> dict[str, Any]:
    """Download only the selected range, falling back to the full source when range transport fails."""
    import yt_dlp
    from yt_dlp.utils import download_range_func

    destination.mkdir(parents=True, exist_ok=True)
    padding = settings.range_download_padding_seconds
    requested_start = max(0.0, start - padding)
    requested_end = end + padding
    base = {
        **_youtube_options(),
        "format": (f"bestvideo[height<={settings.download_max_height}]+bestaudio/"
                   f"best[height<={settings.download_max_height}]"),
        "outtmpl": str(destination / "selected.%(ext)s"), "merge_output_format": "mp4",
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "retries": 2, "fragment_retries": 2, "socket_timeout": 20,
    }
    range_error = ""
    try:
        options = {**base, "download_ranges": download_range_func(None, [(requested_start, requested_end)])}
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
        video = _first_media(destination, "selected", {".mp4", ".mkv", ".webm", ".mov"})
        if video is None:
            raise RuntimeError("range download produced no video")
        return {"video": video, "info": info, "media_start": requested_start,
                "range_downloaded": True, "range_error": ""}
    except Exception as exc:
        range_error = str(exc)

    for partial in destination.glob("selected.*"):
        if partial.is_file():
            partial.unlink(missing_ok=True)
    fallback_options = {**base, "outtmpl": str(destination / "fallback_full.%(ext)s")}
    with yt_dlp.YoutubeDL(fallback_options) as downloader:
        info = downloader.extract_info(url, download=True)
    video = _first_media(destination, "fallback_full", {".mp4", ".mkv", ".webm", ".mov"})
    if video is None:
        raise RuntimeError(f"range and fallback downloads failed: {range_error}")
    return {"video": video, "info": info, "media_start": 0.0,
            "range_downloaded": False, "range_error": range_error}


def download_source(url: str, destination: Path, settings: Settings) -> dict[str, Any]:
    import yt_dlp
    destination.mkdir(parents=True, exist_ok=True)
    template = str(destination / "source.%(ext)s")
    options = {
        **_youtube_options(),
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


def download_reddit_video(post_url: str, destination: Path, maximum_height: int = 1080,
                          direct_video_url: str = "") -> dict[str, Any]:
    """Download a Reddit-hosted video and merge its DASH audio when one exists."""
    import yt_dlp
    destination.mkdir(parents=True, exist_ok=True)
    base_options = {
        "format": f"bestvideo[height<={maximum_height}]+bestaudio/best[height<={maximum_height}]/best",
        "outtmpl": str(destination / "reddit-source.%(ext)s"),
        "merge_output_format": "mp4", "quiet": True, "no_warnings": True,
        "noplaylist": True, "retries": 3, "fragment_retries": 3, "socket_timeout": 25,
        "http_headers": {"User-Agent": "horror-shorts-automation/3.0"},
    }
    errors: list[str] = []
    info: dict[str, Any] | None = None
    targets = []
    if direct_video_url.startswith("https://v.redd.it/"):
        targets.append((direct_video_url.rstrip("/") + "/DASHPlaylist.mpd", True))
    targets.append((post_url, False))
    for target, generic in targets:
        try:
            options = {**base_options, "force_generic_extractor": generic}
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(target, download=True)
            break
        except Exception as exc:
            errors.append(f"{target}: {exc}")
    if info is None:
        raise RuntimeError("Reddit CDN and post downloads failed: " + " | ".join(errors))
    video = _first_media(destination, "reddit-source", {".mp4", ".mkv", ".webm", ".mov"})
    if video is None:
        raise RuntimeError("Reddit video download produced no playable media")
    return {"video": video, "info": info}


def use_local_source(source: Path, destination: Path) -> dict[str, Any]:
    if not source.is_file() or source.stat().st_size == 0:
        raise FileNotFoundError(source)
    sidecar = source.with_suffix(".vtt")
    return {"video": source.resolve(), "subtitles": sidecar.resolve() if sidecar.is_file() else None,
            "info": {"id": source.stem, "title": source.stem, "webpage_url": str(source),
                     "channel": "local authorized source", "channel_id": "local", "duration": None}}
