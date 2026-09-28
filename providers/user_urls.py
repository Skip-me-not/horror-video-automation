from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
from pathlib import Path
from urllib.parse import urlsplit

import requests
from PIL import Image

from src.utils import ffprobe

LICENSES = {"CC0-1.0", "CC-BY-4.0", "PUBLIC-DOMAIN", "OWNED", "PERMISSION-GRANTED"}
MAX_BYTES = 50 * 1024 * 1024


def approved_record(root: Path, url: str) -> dict:
    path = root / "config" / "telegram_media_approvals.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload.get("assets", []):
        if item.get("url") == url and item.get("license") in LICENSES and all(
            item.get(key) for key in ("source_url", "permission_evidence_url", "attribution")
        ):
            return item
    raise ValueError("MEDIA URL has no exact source/permission approval record")


def _public_https(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("media URL must use public HTTPS")
    for result in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(result[4][0]).is_global:
            raise ValueError("media URL resolves to a non-public address")


def download(url: str, root: Path, cache: Path, *, session: requests.Session | None = None,
             approved: dict | None = None) -> dict:
    record = approved or approved_record(root, url)
    if record.get("url") != url:
        raise ValueError("approval URL does not match the requested asset")
    _public_https(url)
    suffix = Path(urlsplit(url).path).suffix.casefold()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".mp4"}:
        raise ValueError("unsupported media format")
    path = cache / (hashlib.sha256(url.encode()).hexdigest() + suffix)
    cache.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        response = (session or requests.Session()).get(url, stream=True, timeout=25, allow_redirects=False)
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError("media redirects are not followed")
        mime = response.headers.get("Content-Type", "").split(";")[0].lower()
        if not (mime.startswith("image/") if suffix != ".mp4" else mime in {"video/mp4", "application/octet-stream"}):
            raise ValueError("media MIME type does not match the asset")
        temporary = path.with_suffix(path.suffix + ".part")
        size = 0
        try:
            with temporary.open("wb") as stream:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("media exceeds 50 MiB")
                    stream.write(chunk)
            if size < 1000:
                raise ValueError("media file is too small")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if suffix == ".mp4":
        probe = ffprobe(path)
        if not any(stream.get("codec_type") == "video" for stream in probe.get("streams", [])):
            raise ValueError("downloaded video has no video stream")
        kind = "video"
    else:
        with Image.open(path) as image:
            image.verify()
        kind = "image"
    return {"id": hashlib.sha256(url.encode()).hexdigest()[:16], "path": str(path), "type": kind,
            "source_url": record["source_url"], "permission_evidence_url": record["permission_evidence_url"],
            "license": record["license"], "attribution": record["attribution"]}
