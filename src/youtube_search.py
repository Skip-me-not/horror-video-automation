from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

from .config_loader import Settings


@dataclass(frozen=True)
class SourceResult:
    video_id: str
    url: str
    title: str
    duration: float
    channel: str
    channel_id: str
    live_status: str
    license: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _reuse_allowed(license_name: str) -> bool:
    normalized = license_name.casefold()
    return "creative commons" in normalized or "reuse allowed" in normalized


def filter_results(entries: list[dict[str, Any]], settings: Settings,
                   history_ids: set[str]) -> list[SourceResult]:
    results: list[SourceResult] = []
    for entry in entries:
        video_id = str(entry.get("id") or "")
        duration = float(entry.get("duration") or 0)
        result = SourceResult(
            video_id=video_id,
            url=str(entry.get("webpage_url") or entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"),
            title=str(entry.get("title") or "Untitled source"),
            duration=duration,
            channel=str(entry.get("channel") or entry.get("uploader") or ""),
            channel_id=str(entry.get("channel_id") or entry.get("uploader_id") or ""),
            live_status=str(entry.get("live_status") or "not_live"),
            license=str(entry.get("license") or ""),
        )
        if not video_id or video_id in history_ids:
            continue
        if not settings.min_source_duration <= duration <= settings.max_source_duration:
            continue
        if result.live_status != "not_live":
            continue
        if settings.require_reuse_license_for_search and not _reuse_allowed(result.license):
            continue
        results.append(result)
    return results


def search(keyword: str, videos_per_keyword: int, settings: Settings,
           history_ids: set[str]) -> list[SourceResult]:
    import yt_dlp
    options = {"quiet": True, "no_warnings": True, "skip_download": True,
               "extract_flat": False, "playlistend": max(1, videos_per_keyword)}
    query = quote_plus(keyword)
    # YouTube's Creative Commons filter. Metadata is still checked below before acceptance.
    search_url = f"https://www.youtube.com/results?search_query={query}&sp=EgIwAQ%253D%253D"
    with yt_dlp.YoutubeDL(options) as downloader:
        payload = downloader.extract_info(search_url, download=False)
    return filter_results(list(payload.get("entries") or []), settings, history_ids)


def inspect_url(url: str) -> dict[str, Any]:
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as downloader:
        return downloader.extract_info(url, download=False)


def assert_authorized(info: dict[str, Any], settings: Settings, explicit_confirmation: bool) -> None:
    if not settings.authorization_required or explicit_confirmation:
        return
    raise PermissionError("manual remote URLs require --authorized confirmation of reuse rights")
