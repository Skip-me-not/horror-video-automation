from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


MEDIA_EXTENSIONS = {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class VisualAsset:
    path: Path
    provider: str
    source_url: str = ""
    credit: str = ""
    license: str = "local/user-provided"


class VisualProvider(ABC):
    @abstractmethod
    def obtain(self, scene: dict[str, Any], slot: int) -> VisualAsset:
        raise NotImplementedError


class LocalAssetProvider(VisualProvider):
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def obtain(self, scene: dict[str, Any], slot: int) -> VisualAsset:
        files = sorted(path for path in self.directory.rglob("*") if path.suffix.casefold() in MEDIA_EXTENSIONS)
        if not files:
            raise FileNotFoundError(f"no local visuals in {self.directory}")
        seed = hashlib.sha256(f"{scene.get('visual_prompt')}:{slot}".encode()).digest()
        return VisualAsset(files[int.from_bytes(seed[:4], "big") % len(files)], "local")


class PexelsVideoProvider(VisualProvider):
    endpoint = "https://api.pexels.com/videos/search"

    def __init__(self, api_key: str, output_dir: Path, timeout: int = 30) -> None:
        if not api_key:
            raise ValueError("PEXELS_API_KEY is required")
        self.api_key, self.output_dir, self.timeout = api_key, output_dir, timeout

    def obtain(self, scene: dict[str, Any], slot: int) -> VisualAsset:
        query = " ".join(scene.get("keywords", [])[:5]) or "dark empty hallway night"
        response = requests.get(self.endpoint, params={"query": query, "orientation": "portrait", "per_page": 15},
                                headers={"Authorization": self.api_key}, timeout=self.timeout)
        response.raise_for_status()
        videos = response.json().get("videos", [])
        if not videos:
            raise RuntimeError(f"Pexels returned no video for {query!r}")
        video = videos[slot % len(videos)]
        files = [item for item in video.get("video_files", []) if item.get("link")]
        if not files:
            raise RuntimeError("Pexels result has no downloadable file")
        selected = min(files, key=lambda item: abs(int(item.get("height") or 0) - 1920))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"pexels-{video['id']}-{slot}.mp4"
        with requests.get(selected["link"], timeout=self.timeout, stream=True) as download:
            download.raise_for_status()
            with path.open("wb") as stream:
                for chunk in download.iter_content(1024 * 1024):
                    stream.write(chunk)
        return VisualAsset(path, "pexels", video.get("url", ""),
                           f"Video by {video.get('user', {}).get('name', 'Pexels creator')} on Pexels", "Pexels license")


def create_visual_provider(root: Path, output_dir: Path) -> VisualProvider:
    key = os.getenv("PEXELS_API_KEY", "")
    if key:
        return PexelsVideoProvider(key, output_dir / "visuals")
    return LocalAssetProvider(root / "assets" / "backgrounds")
