from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from PIL import Image, UnidentifiedImageError

from src.utils import ffprobe

ALLOWED_HOSTS = {"i.redd.it", "preview.redd.it", "v.redd.it"}
MAX_BYTES = 50 * 1024 * 1024


def download_approved(candidate: dict[str, Any], destination: Path,
                      session: requests.Session | None = None) -> dict[str, Any]:
    if not candidate.get("approved_for_use") or not candidate.get("permission_evidence_url"):
        raise ValueError("media lacks a recorded rights approval")
    url = str(candidate.get("media_url", ""))
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("media URL is not on an allowed Reddit media host")
    media_type = str(candidate.get("media_type", ""))
    if media_type not in {"image", "video"}:
        raise ValueError("unsupported media type")
    destination.mkdir(parents=True, exist_ok=True)
    index = len(list(destination.glob("[0-9][0-9][0-9]_*"))) + 1
    suffix = ".mp4" if media_type == "video" else ".jpg"
    path = destination / f"{index:03d}_{media_type}{suffix}"
    temporary = path.with_suffix(path.suffix + ".part")
    session = session or requests.Session()
    try:
        with session.get(url, timeout=(10, 30), stream=True, allow_redirects=False,
                         headers={"User-Agent": "LululalaRightsAwareMedia/1.0"}) as response:
            response.raise_for_status()
            if response.status_code >= 300:
                raise ValueError("approved media URL redirected; reapproval is required")
            if urlsplit(response.url).hostname not in ALLOWED_HOSTS:
                raise ValueError("media download redirected outside the allowed host list")
            content_type = response.headers.get("Content-Type", "").lower()
            if media_type == "image" and not content_type.startswith("image/"):
                raise ValueError("approved image URL did not return an image")
            if media_type == "video" and not (content_type.startswith("video/") or "octet-stream" in content_type):
                raise ValueError("approved video URL did not return video bytes")
            size = 0
            with temporary.open("wb") as stream:
                for block in response.iter_content(chunk_size=256 * 1024):
                    size += len(block)
                    if size > MAX_BYTES:
                        raise ValueError("media exceeds 50 MiB download limit")
                    stream.write(block)
        if size < 1024:
            raise ValueError("download is corrupt or too small")
        if media_type == "image":
            with Image.open(temporary) as image:
                image.verify()
            with Image.open(temporary) as image:
                if image.width < 320 or image.height < 320:
                    raise ValueError("image resolution is too low")
        else:
            probe = ffprobe(temporary)
            streams = probe.get("streams", [])
            if not any(item.get("codec_type") == "video" for item in streams):
                raise ValueError("download has no playable video stream")
            if float(probe.get("format", {}).get("duration") or 0) < 1.5:
                raise ValueError("approved clip is too short for a contextual edit")
        shutil.move(str(temporary), str(path))
        return {**candidate, "local_path": str(path),
                "downloaded_at": datetime.now(timezone.utc).isoformat(), "bytes": size}
    except (requests.RequestException, OSError, UnidentifiedImageError, ValueError):
        temporary.unlink(missing_ok=True)
        raise
