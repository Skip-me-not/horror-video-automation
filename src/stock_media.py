from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

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
        asset = (self.search_reference_video(query) if prefer_video else self.search_reference_image(query))
        if asset is None:
            asset = (self.search_reference_image(query) if prefer_video else self.search_reference_video(query))
        if asset is None:
            return None
        suffix = ".mp4" if asset.media_type == "video" else ".jpg"
        target = self.directory / f"{asset.provider}-{safe_filename(asset.asset_id)}{suffix}"
        if not target.is_file():
            response = self.session.get(asset.download_url, timeout=45, stream=True)
            response.raise_for_status()
            with target.open("wb") as output:
                for chunk in response.iter_content(1024 * 256):
                    if chunk:
                        output.write(chunk)
        if target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            return None
        return StockAsset(**{**asset.as_dict(), "local_path": str(target)})

    def _pexels_video(self, query: str) -> StockAsset | None:
        key = os.getenv("PEXELS_API_KEY", "")
        if not self.enable_pexels or not key:
            return None
        response = self.session.get("https://api.pexels.com/videos/search", params={"query": query, "per_page": 5},
                                    headers={"Authorization": key}, timeout=30)
        response.raise_for_status()
        videos = response.json().get("videos", [])
        for video in videos:
            files = sorted(video.get("video_files", []), key=lambda item: abs(int(item.get("height") or 0) - 1080))
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
                                    headers={"Authorization": key}, timeout=30)
        response.raise_for_status()
        photos = response.json().get("photos", [])
        if not photos:
            return None
        photo = photos[0]
        return StockAsset("pexels", "image", str(photo["id"]), str(photo.get("photographer") or "Unknown"),
                          str(photo.get("url") or ""), "Pexels license; verify source page",
                          str((photo.get("src") or {}).get("large2x") or (photo.get("src") or {}).get("large")))

    def _pixabay_video(self, query: str) -> StockAsset | None:
        key = os.getenv("PIXABAY_API_KEY", "")
        if not self.enable_pixabay or not key:
            return None
        response = self.session.get("https://pixabay.com/api/videos/",
                                    params={"key": key, "q": query, "per_page": 5, "safesearch": "true"}, timeout=30)
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
                                            "image_type": "photo"}, timeout=30)
        response.raise_for_status()
        hits = response.json().get("hits", [])
        if not hits:
            return None
        hit = hits[0]
        return StockAsset("pixabay", "image", str(hit["id"]), str(hit.get("user") or "Unknown"),
                          str(hit.get("pageURL") or ""), "Pixabay Content License; verify source page",
                          str(hit.get("largeImageURL") or hit.get("webformatURL") or ""))
