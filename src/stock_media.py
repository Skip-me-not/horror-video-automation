from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .utils import safe_filename


@dataclass(frozen=True)
class StockAsset:
    provider: str
    media_type: str
    asset_id: str
    creator: str
    source_page: str
    license_information: str
    download_url: str
    local_path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class StockMediaClient:
    def __init__(self, directory: Path, enable_pexels: bool = True, enable_pixabay: bool = True) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.enable_pexels = enable_pexels
        self.enable_pixabay = enable_pixabay
        self.session = requests.Session()
        retry = Retry(total=2, connect=2, read=2, backoff_factor=0.35,
                      status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.query_result_cache: dict[tuple[str, bool], StockAsset | None] = {}
        self.downloaded_asset_cache: dict[str, Path] = {}

    def search_reference_video(self, query: str) -> StockAsset | None:
        return self._first_available((self._pexels_video, self._pixabay_video), query)

    def search_reference_image(self, query: str) -> StockAsset | None:
        return self._first_available((self._pexels_image, self._pixabay_image), query)

    @staticmethod
    def _first_available(providers: tuple[Any, ...], query: str) -> StockAsset | None:
        for provider in providers:
            try:
                asset = provider(query)
            except (requests.RequestException, KeyError, TypeError, ValueError):
                asset = None
            if asset:
                return asset
        return None

    def acquire(self, query: str, prefer_video: bool = True) -> StockAsset | None:
        cache_key = (query.casefold().strip(), prefer_video)
        if cache_key in self.query_result_cache:
            return self.query_result_cache[cache_key]
        asset = (self.search_reference_video(query) if prefer_video else self.search_reference_image(query))
        if asset is None:
            asset = (self.search_reference_image(query) if prefer_video else self.search_reference_video(query))
        if asset is None:
            self.query_result_cache[cache_key] = None
            return None
        suffix = ".mp4" if asset.media_type == "video" else ".jpg"
        target = self.directory / f"{asset.provider}-{safe_filename(asset.asset_id)}{suffix}"
        cached_path = self.downloaded_asset_cache.get(asset.download_url)
        if cached_path and cached_path.is_file():
            result = StockAsset(**{**asset.as_dict(), "local_path": str(cached_path)})
            self.query_result_cache[cache_key] = result
            return result
        if not target.is_file():
            response = self.session.get(asset.download_url, timeout=20, stream=True)
            response.raise_for_status()
            with target.open("wb") as output:
                for chunk in response.iter_content(1024 * 256):
                    if chunk:
                        output.write(chunk)
        if target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            self.query_result_cache[cache_key] = None
            return None
        self.downloaded_asset_cache[asset.download_url] = target
        result = StockAsset(**{**asset.as_dict(), "local_path": str(target)})
        self.query_result_cache[cache_key] = result
        return result

    def _pexels_video(self, query: str) -> StockAsset | None:
        key = os.getenv("PEXELS_API_KEY", "")
        if not self.enable_pexels or not key:
            return None
        response = self.session.get("https://api.pexels.com/videos/search", params={"query": query, "per_page": 5},
                                    headers={"Authorization": key}, timeout=15)
        response.raise_for_status()
        videos = response.json().get("videos", [])
        for video in videos:
            files = sorted(video.get("video_files", []),
                           key=lambda item: ((int(item.get("height") or 0) > 900),
                                             0 if int(item.get("height") or 0) >= int(item.get("width") or 0) else 1,
                                             abs(int(item.get("height") or 0) - 720)))
            chosen = next((item for item in files if item.get("link")), None)
            if chosen:
                user = video.get("user") or {}
                return StockAsset("pexels", "video", str(video["id"]), str(user.get("name") or "Unknown"),
                                  str(video.get("url") or ""), "Pexels license; verify source page", chosen["link"])
        return None

    def _pexels_image(self, query: str) -> StockAsset | None:
        key = os.getenv("PEXELS_API_KEY", "")
        if not self.enable_pexels or not key:
            return None
        response = self.session.get("https://api.pexels.com/v1/search", params={"query": query, "per_page": 5},
                                    headers={"Authorization": key}, timeout=15)
        response.raise_for_status()
        photos = response.json().get("photos", [])
        if not photos:
            return None
        photo = photos[0]
        return StockAsset("pexels", "image", str(photo["id"]), str(photo.get("photographer") or "Unknown"),
                          str(photo.get("url") or ""), "Pexels license; verify source page",
                          str((photo.get("src") or {}).get("large") or (photo.get("src") or {}).get("medium")))

    def _pixabay_video(self, query: str) -> StockAsset | None:
        key = os.getenv("PIXABAY_API_KEY", "")
        if not self.enable_pixabay or not key:
            return None
        response = self.session.get("https://pixabay.com/api/videos/",
                                    params={"key": key, "q": query, "per_page": 5, "safesearch": "true"}, timeout=15)
        response.raise_for_status()
        hits = response.json().get("hits", [])
        if not hits:
            return None
        hit = hits[0]
        videos = hit.get("videos") or {}
        chosen = videos.get("medium") or videos.get("small") or videos.get("large") or {}
        return StockAsset("pixabay", "video", str(hit["id"]), str(hit.get("user") or "Unknown"),
                          str(hit.get("pageURL") or ""), "Pixabay Content License; verify source page",
                          str(chosen.get("url") or "")) if chosen.get("url") else None

    def _pixabay_image(self, query: str) -> StockAsset | None:
        key = os.getenv("PIXABAY_API_KEY", "")
        if not self.enable_pixabay or not key:
            return None
        response = self.session.get("https://pixabay.com/api/",
                                    params={"key": key, "q": query, "per_page": 5, "safesearch": "true",
                                            "image_type": "photo"}, timeout=15)
        response.raise_for_status()
        hits = response.json().get("hits", [])
        if not hits:
            return None
        hit = hits[0]
        return StockAsset("pixabay", "image", str(hit["id"]), str(hit.get("user") or "Unknown"),
                          str(hit.get("pageURL") or ""), "Pixabay Content License; verify source page",
                          str(hit.get("largeImageURL") or hit.get("webformatURL") or ""))
