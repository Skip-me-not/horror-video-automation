from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path

import requests

from .user_urls import download

ALLOWED = {"CC0", "CC0 1.0", "CC BY 4.0", "PUBLIC DOMAIN"}


def search(person: str, root: Path, cache: Path, *, session: requests.Session | None = None,
           limit: int = 5) -> list[dict]:
    client = session or requests.Session()
    response = client.get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": person,
        "gsrnamespace": 6, "gsrlimit": min(limit * 3, 15), "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": 1600,
    }, timeout=20)
    response.raise_for_status()
    results = []
    for page in response.json().get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_name = re.sub(r"<[^>]+>", "", str(meta.get("LicenseShortName", {}).get("value", ""))).strip().upper()
        if license_name not in ALLOWED:
            continue
        url = info.get("thumburl") or info.get("url")
        if not url or not url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        source = info.get("descriptionurl") or ""
        if not source.startswith("https://commons.wikimedia.org/"):
            continue
        credit = html.unescape(re.sub(r"<[^>]+>", "", str(meta.get("Artist", {}).get("value", ""))))[:100]
        record = {"url": url, "source_url": source, "permission_evidence_url": source,
                  "license": "CC0-1.0" if "CC0" in license_name else "PUBLIC-DOMAIN" if "PUBLIC" in license_name else "CC-BY-4.0",
                  "attribution": credit or "Wikimedia Commons contributor"}
        try:
            item = download(url, root, cache, session=client, approved=record)
            item["id"] = hashlib.sha256(source.encode()).hexdigest()[:16]
            results.append(item)
        except (OSError, ValueError, requests.RequestException):
            continue
        if len(results) >= limit:
            break
    return results
