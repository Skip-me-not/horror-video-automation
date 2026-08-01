from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

try:
    from scripts.common import ValidationError, load_config, load_json
except ModuleNotFoundError:
    from common import ValidationError, load_config, load_json

API_URL = "https://api.pexels.com/v1/videos/search"


def select_video_file(payload: dict[str, Any], job_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for video in payload.get("videos", []):
        for item in video.get("video_files", []):
            link = str(item.get("link", ""))
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
            if (
                item.get("file_type") == "video/mp4"
                and link.startswith("https://")
                and urlparse(link).hostname == "videos.pexels.com"
                and height > width
                and width >= 720
                and height >= 1280
            ):
                candidates.append((video, item))
    if not candidates:
        raise ValidationError("Pexels returned no suitable portrait MP4")
    candidates.sort(
        key=lambda pair: (
            abs(int(pair[1]["width"]) - 1080) + abs(int(pair[1]["height"]) - 1920),
            int(pair[0].get("id") or 0),
        )
    )
    shortlist = candidates[: min(8, len(candidates))]
    seed = int.from_bytes(hashlib.sha256(job_id.encode("utf-8")).digest()[:8], "big")
    return shortlist[seed % len(shortlist)]


def add_credit(description: str, video: dict[str, Any]) -> str:
    creator = str(video.get("user", {}).get("name") or "Pexels contributor").strip()
    page_url = str(video.get("url") or "https://www.pexels.com").strip()
    credit = f"Background video by {creator} on Pexels: {page_url}"
    cleaned = description.rstrip()
    if credit in cleaned:
        return cleaned
    available = max(0, 5000 - len(credit) - 2)
    return f"{cleaned[:available].rstrip()}\n\n{credit}".strip()


def get_json(url: str, headers: dict[str, str], params: dict[str, object]) -> dict[str, Any]:
    request = Request(f"{url}?{urlencode(params)}", headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def download_file(url: str, destination: Path, max_bytes: int) -> int:
    written = 0
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": "horror-shorts-automation/1.0"})
    try:
        with urlopen(request, timeout=90) as response:
            if urlparse(response.geturl()).hostname != "videos.pexels.com":
                raise ValidationError("Pexels media redirected outside its video CDN")
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type and "video" not in content_type and "octet-stream" not in content_type:
                raise ValidationError(f"unexpected Pexels media type: {content_type}")
            length = int(response.headers.get("Content-Length") or 0)
            if length > max_bytes:
                raise ValidationError("Pexels video exceeds download size limit")
            with temporary.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValidationError("Pexels video exceeds download size limit")
                    handle.write(chunk)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    if written < 1024:
        raise ValidationError("Pexels video download was empty")
    temporary.replace(destination)
    return written


def fetch(job_path: Path, config_path: Path, project: Path) -> dict[str, Any]:
    job = load_json(job_path)
    config = load_config(config_path)
    key = os.getenv("PEXELS_API_KEY", "").strip()
    report_path = project / config["output_directory"] / "background-source.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if not key:
        report = {"status": "fallback", "reason": "PEXELS_API_KEY is not configured",
                  "background_file": job["background_file"]}
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    query = str(job.get("background_query") or config["pexels_default_query"])
    payload = get_json(
        API_URL,
        {"Authorization": key, "User-Agent": "horror-shorts-automation/1.0"},
        {"query": query, "orientation": "portrait", "size": "medium",
         "locale": "en-US", "per_page": 24},
    )
    video, media = select_video_file(payload, job["job_id"])
    filename = f"pexels-{job['job_id']}.mp4"
    destination = project / "assets" / "backgrounds" / filename
    size = download_file(str(media["link"]), destination, int(config["pexels_max_download_bytes"]))
    job["background_file"] = filename
    job["description"] = add_credit(job["description"], video)
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    report = {
        "status": "downloaded",
        "provider": "Pexels",
        "query": query,
        "video_id": video.get("id"),
        "creator": video.get("user", {}).get("name"),
        "source_url": video.get("url"),
        "width": media.get("width"),
        "height": media.get("height"),
        "bytes": size,
        "background_file": filename,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", default="output/job.json")
    parser.add_argument("--config", default="config/default.json")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    try:
        report = fetch(Path(args.job), Path(args.config), project)
    except (HTTPError, URLError, ValidationError, OSError, ValueError, json.JSONDecodeError) as exc:
        job = load_json(args.job)
        output = project / "output" / "background-source.json"
        report = {"status": "fallback", "reason": str(exc),
                  "background_file": job["background_file"]}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
