from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

try:
    from scripts.common import (
        ValidationError, desired_background_scenes, effective_video_duration,
        load_config, load_json,
    )
except ModuleNotFoundError:
    from common import (
        ValidationError, desired_background_scenes, effective_video_duration,
        load_config, load_json,
    )

PEXELS_VIDEO_URL = "https://api.pexels.com/v1/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"
ARCHIVE_SEARCH_URL = "https://archive.org/advancedsearch.php"
ARCHIVE_METADATA_URL = "https://archive.org/metadata/"
USER_AGENT = "horror-shorts-automation/2.0 (https://github.com/Skip-me-not/horror-video-automation)"
ALLOWED_COMMONS_LICENSES = {
    "cc0", "public domain", "cc by 4.0", "cc by 3.0", "cc by 2.0",
    "cc by-sa 4.0", "cc by-sa 3.0", "cc by-sa 2.0",
}


def seeded_number(seed: str, modulo: int) -> int:
    if modulo < 1:
        raise ValueError("modulo must be positive")
    return int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big") % modulo


def get_json(url: str, headers: dict[str, str], params: dict[str, object] | None = None) -> dict[str, Any]:
    target = f"{url}?{urlencode(params, doseq=True)}" if params else url
    request = Request(target, headers={"User-Agent": USER_AGENT, **headers})
    with urlopen(request, timeout=35) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValidationError("media API returned an invalid response")
    return value


def orientation_score(width: int, height: int) -> tuple[int, float]:
    if width <= 0 or height <= 0:
        return 3, 99.0
    ratio = width / height
    return (0 if height > width else 1, abs(ratio - 9 / 16))


def pexels_media_host(hostname: str | None) -> bool:
    return bool(hostname) and (
        hostname == "videos.pexels.com" or hostname == "player.vimeo.com"
        or hostname.endswith(".akamaized.net")
    )


def select_video_file(
    payload: dict[str, Any], job_id: str, used_ids: set[int] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Choose a usable Pexels MP4, preferring portrait without requiring it."""
    used_ids = used_ids or set()
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for video in payload.get("videos", []):
        video_id = int(video.get("id") or 0)
        if not video_id or video_id in used_ids:
            continue
        for media in video.get("video_files", []):
            link = str(media.get("link", ""))
            width, height = int(media.get("width") or 0), int(media.get("height") or 0)
            if (
                media.get("file_type") == "video/mp4"
                and link.startswith("https://")
                and pexels_media_host(urlparse(link).hostname)
                and min(width, height) >= 720
            ):
                candidates.append((video, media))
    if not candidates:
        raise ValidationError("Pexels returned no suitable unused MP4")
    candidates.sort(key=lambda pair: (*orientation_score(int(pair[1]["width"]), int(pair[1]["height"])), int(pair[0]["id"])))
    shortlist = candidates[: min(40, len(candidates))]
    return shortlist[seeded_number(job_id, len(shortlist))]


def select_pixabay_video(
    payload: dict[str, Any], seed: str, used: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    used = used or set()
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for video in payload.get("hits", []):
        video_id = int(video.get("id") or 0)
        if not video_id or f"pixabay:{video_id}" in used:
            continue
        renditions = []
        for name in ("medium", "large", "small"):
            media = video.get("videos", {}).get(name, {})
            width, height = int(media.get("width") or 0), int(media.get("height") or 0)
            url = str(media.get("url", ""))
            if min(width, height) >= 720 and urlparse(url).hostname == "cdn.pixabay.com":
                renditions.append(media)
        if renditions:
            renditions.sort(key=lambda item: (*orientation_score(int(item["width"]), int(item["height"])), int(item.get("size") or 0)))
            candidates.append((video, renditions[0]))
    if not candidates:
        raise ValidationError("Pixabay returned no suitable unused MP4")
    candidates.sort(key=lambda pair: (*orientation_score(int(pair[1]["width"]), int(pair[1]["height"])), int(pair[0]["id"])))
    shortlist = candidates[: min(60, len(candidates))]
    return shortlist[seeded_number(seed, len(shortlist))]


def clean_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def metadata_value(metadata: dict[str, Any], key: str) -> str:
    item = metadata.get(key, {})
    return clean_html(str(item.get("value", ""))) if isinstance(item, dict) else ""


def select_commons_video(
    payload: dict[str, Any], seed: str, used: set[str], max_bytes: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    pages = payload.get("query", {}).get("pages", [])
    if isinstance(pages, dict):
        pages = list(pages.values())
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for page in pages:
        page_id = int(page.get("pageid") or 0)
        info_list = page.get("imageinfo", [])
        if not page_id or f"wikimedia:{page_id}" in used or not info_list:
            continue
        info = info_list[0]
        width, height = int(info.get("width") or 0), int(info.get("height") or 0)
        license_name = metadata_value(info.get("extmetadata", {}), "LicenseShortName").lower()
        if (
            info.get("mime") in {"video/webm", "video/ogg"}
            and min(width, height) >= 480
            and 1024 <= int(info.get("size") or 0) <= max_bytes
            and urlparse(str(info.get("url", ""))).hostname == "upload.wikimedia.org"
            and license_name in ALLOWED_COMMONS_LICENSES
        ):
            candidates.append((page, info))
    if not candidates:
        raise ValidationError("Wikimedia Commons returned no suitable licensed video")
    candidates.sort(key=lambda pair: (*orientation_score(int(pair[1]["width"]), int(pair[1]["height"])), int(pair[0]["pageid"])))
    shortlist = candidates[: min(30, len(candidates))]
    return shortlist[seeded_number(seed, len(shortlist))]


def add_credit(description: str, video: dict[str, Any]) -> str:
    creator = str(video.get("user", {}).get("name") or "Pexels contributor").strip()
    page_url = str(video.get("url") or "https://www.pexels.com/videos/").strip()
    credit = f"Background video by {creator} on Pexels: {page_url}"
    if credit in description:
        return description
    return f"{description.rstrip()}\n\n{credit}".strip()[:5000]


def fetch_pexels(query: str, seed: str, key: str, used: set[str]) -> tuple[dict[str, Any], str, str]:
    params: dict[str, object] = {
        "query": query, "orientation": "portrait", "size": "medium", "locale": "en-US",
        "per_page": 80, "page": seeded_number(f"{seed}:pexels-page", 5) + 1,
    }
    payload = get_json(PEXELS_VIDEO_URL, {"Authorization": key}, params)
    try:
        video, media = select_video_file(payload, seed, {int(item.split(":", 1)[1]) for item in used if item.startswith("pexels:")})
    except ValidationError:
        params.pop("orientation", None)
        params["page"] = 1
        payload = get_json(PEXELS_VIDEO_URL, {"Authorization": key}, params)
        video, media = select_video_file(payload, seed, {int(item.split(":", 1)[1]) for item in used if item.startswith("pexels:")})
    return ({
        "provider": "Pexels", "media_id": f"pexels:{video['id']}",
        "creator": video.get("user", {}).get("name") or "Pexels contributor",
        "source_url": video.get("url") or "https://www.pexels.com/videos/", "query": query,
    }, str(media["link"]), ".mp4")


def fetch_pixabay(query: str, seed: str, key: str, used: set[str]) -> tuple[dict[str, Any], str, str]:
    params: dict[str, object] = {
        "key": key, "q": query, "lang": "en", "video_type": "film", "safesearch": "true",
        "order": "latest", "per_page": 100, "page": seeded_number(f"{seed}:pixabay-page", 5) + 1,
        "min_width": 720, "min_height": 720,
    }
    payload = get_json(PIXABAY_VIDEO_URL, {}, params)
    try:
        video, media = select_pixabay_video(payload, seed, used)
    except ValidationError:
        params["page"] = 1
        payload = get_json(PIXABAY_VIDEO_URL, {}, params)
        video, media = select_pixabay_video(payload, seed, used)
    return ({
        "provider": "Pixabay", "media_id": f"pixabay:{video['id']}",
        "creator": video.get("user") or "Pixabay contributor",
        "source_url": video.get("pageURL") or "https://pixabay.com/videos/", "query": query,
    }, str(media["url"]), ".mp4")


def fetch_wikimedia(query: str, seed: str, used: set[str], max_bytes: int) -> tuple[dict[str, Any], str, str]:
    params: dict[str, object] = {
        "action": "query", "format": "json", "formatversion": 2, "generator": "search",
        "gsrsearch": f"{query} filetype:video", "gsrnamespace": 6, "gsrlimit": 50,
        "gsroffset": seeded_number(f"{seed}:commons-offset", 4) * 50,
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|Credit",
        "iiextmetadatalanguage": "en",
    }
    payload = get_json(WIKIMEDIA_API_URL, {}, params)
    try:
        page, info = select_commons_video(payload, seed, used, max_bytes)
    except ValidationError:
        params["gsroffset"] = 0
        payload = get_json(WIKIMEDIA_API_URL, {}, params)
        page, info = select_commons_video(payload, seed, used, max_bytes)
    metadata = info.get("extmetadata", {})
    extension = ".webm" if info.get("mime") == "video/webm" else ".ogv"
    return ({
        "provider": "Wikimedia Commons", "media_id": f"wikimedia:{page['pageid']}",
        "creator": metadata_value(metadata, "Artist") or "Wikimedia Commons contributor",
        "source_url": info.get("descriptionurl") or "https://commons.wikimedia.org/",
        "license": metadata_value(metadata, "LicenseShortName"),
        "license_url": metadata_value(metadata, "LicenseUrl"), "query": query,
    }, str(info["url"]), extension)


def fetch_internet_archive(query: str, seed: str, used: set[str], max_bytes: int) -> tuple[dict[str, Any], str, str]:
    safe_terms = " ".join(re.findall(r"[A-Za-z0-9]+", query)[:8])
    params: dict[str, object] = {
        "q": f'mediatype:movies AND title:({safe_terms}) AND (licenseurl:*creativecommons* OR licenseurl:*publicdomain*)',
        "fl[]": ["identifier", "title", "creator", "licenseurl"], "rows": 30,
        "page": seeded_number(f"{seed}:archive-page", 3) + 1, "output": "json",
    }
    payload = get_json(ARCHIVE_SEARCH_URL, {}, params)
    docs = payload.get("response", {}).get("docs", [])
    if not docs and params["page"] != 1:
        params["page"] = 1
        docs = get_json(ARCHIVE_SEARCH_URL, {}, params).get("response", {}).get("docs", [])
    if not isinstance(docs, list):
        raise ValidationError("Internet Archive returned an invalid search response")
    ordered = sorted(docs, key=lambda item: str(item.get("identifier", "")))
    if ordered:
        offset = seeded_number(seed, len(ordered))
        ordered = ordered[offset:] + ordered[:offset]
    for doc in ordered[:10]:
        identifier = str(doc.get("identifier", ""))
        if not identifier or f"archive:{identifier}" in used:
            continue
        metadata = get_json(f"{ARCHIVE_METADATA_URL}{quote(identifier, safe='')}", {})
        files = []
        for item in metadata.get("files", []):
            name = str(item.get("name", ""))
            try:
                size = int(item.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            if name.lower().endswith(".mp4") and 1024 <= size <= max_bytes and "sample" not in name.lower():
                files.append((size, name))
        if not files:
            continue
        _, name = sorted(files)[-1]
        return ({
            "provider": "Internet Archive", "media_id": f"archive:{identifier}",
            "creator": doc.get("creator") or "Internet Archive contributor",
            "source_url": f"https://archive.org/details/{quote(identifier, safe='')}",
            "license": doc.get("licenseurl") or "Creative Commons / Public Domain",
            "query": query,
        }, f"https://archive.org/download/{quote(identifier, safe='')}/{quote(name)}", ".mp4")
    raise ValidationError("Internet Archive returned no suitable licensed MP4")


def approved_download_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    return (
        pexels_media_host(hostname)
        or hostname in {"cdn.pixabay.com", "upload.wikimedia.org", "archive.org"}
        or hostname.endswith(".archive.org")
    )


def download_file(url: str, destination: Path, max_bytes: int) -> int:
    temporary, written = destination.with_suffix(destination.suffix + ".part"), 0
    try:
        with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=120) as response:
            if not approved_download_host(urlparse(response.geturl()).hostname):
                raise ValidationError("media redirected outside an approved provider CDN")
            length = int(response.headers.get("Content-Length") or 0)
            if length > max_bytes:
                raise ValidationError("background video exceeds the per-scene download limit")
            with temporary.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValidationError("background video exceeds the per-scene download limit")
                    handle.write(chunk)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    if written < 1024:
        temporary.unlink(missing_ok=True)
        raise ValidationError("background video download was empty")
    temporary.replace(destination)
    return written


def provider_order(job_id: str, slot: int, pexels_key: str, pixabay_key: str) -> list[str]:
    providers = (["pexels"] if pexels_key else []) + (["pixabay"] if pixabay_key else []) + ["wikimedia", "archive"]
    start = (seeded_number(f"{job_id}:provider", len(providers)) + slot) % len(providers)
    return providers[start:] + providers[:start]


def credit_line(index: int, record: dict[str, Any]) -> str:
    line = f"Background {index} by {record['creator']} on {record['provider']}: {record['source_url']}"
    if record.get("license"):
        line += f" ({record['license']}{': ' + record['license_url'] if record.get('license_url') else ''})"
    return line


def fetch(job_path: Path, config_path: Path, project: Path) -> dict[str, Any]:
    job, config = load_json(job_path), load_config(config_path)
    output_dir = project / config["output_directory"]
    voice_report = load_json(output_dir / "voice-report.json")
    duration = effective_video_duration(float(voice_report["duration_seconds"]), config, job["job_id"])
    scene_count = desired_background_scenes(duration, config)
    pexels_key, pixabay_key = os.getenv("PEXELS_API_KEY", "").strip(), os.getenv("PIXABAY_API_KEY", "").strip()
    queries = job.get("background_queries") or [job.get("background_query", config["background_default_query"])]
    max_bytes = int(config["background_max_download_bytes"])
    backgrounds_dir = project / "assets" / "backgrounds"
    backgrounds_dir.mkdir(parents=True, exist_ok=True)
    fallback = str(job["background_file"])
    used: set[str] = set()
    filenames: list[str] = []
    records: list[dict[str, Any]] = []
    failures: list[str] = []

    for slot in range(scene_count):
        query = str(queries[slot % len(queries)])
        seed = f"{job['job_id']}:{slot}:{query}"
        selected = False
        for provider in provider_order(job["job_id"], slot, pexels_key, pixabay_key):
            try:
                if provider == "pexels":
                    record, media_url, extension = fetch_pexels(query, seed, pexels_key, used)
                elif provider == "pixabay":
                    record, media_url, extension = fetch_pixabay(query, seed, pixabay_key, used)
                elif provider == "wikimedia":
                    record, media_url, extension = fetch_wikimedia(query, seed, used, max_bytes)
                else:
                    record, media_url, extension = fetch_internet_archive(query, seed, used, max_bytes)
                filename = f"{provider}-{job['job_id']}-{slot + 1}{extension}"
                size = download_file(media_url, backgrounds_dir / filename, max_bytes)
                record.update(bytes=size, background_file=filename)
                record["creator"] = str(record["creator"])[:160]
                filenames.append(filename)
                records.append(record)
                used.add(str(record["media_id"]))
                selected = True
                break
            except (HTTPError, URLError, ValidationError, OSError, ValueError, json.JSONDecodeError) as exc:
                failures.append(f"scene {slot + 1} {provider}: {exc}")
        if not selected:
            filenames.append(fallback)

    job["background_files"] = filenames
    job["background_file"] = filenames[0]
    credits = "\n".join(credit_line(index, record) for index, record in enumerate(records, start=1))
    if credits:
        available = max(0, 5000 - len(credits) - 2)
        job["description"] = f"{job['description'][:available].rstrip()}\n\n{credits}".strip()
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    report = {
        "status": "downloaded" if records else "fallback",
        "target_duration_seconds": duration, "requested_scenes": scene_count,
        "downloaded_scenes": len(records), "backgrounds": records,
        "providers": {"pexels": bool(pexels_key), "pixabay": bool(pixabay_key), "wikimedia_commons": True, "internet_archive": True},
        "provider_failures": failures,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "background-source.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", default="output/job.json")
    parser.add_argument("--config", default="config/default.json")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    report = fetch(Path(args.job), Path(args.config), project)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
