from __future__ import annotations

import argparse
import json
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from scripts.upload_youtube import credentials_from_environment, execute_resumable

from .job import validate_job


def upload(video: Path, job: dict, privacy: str = "private") -> dict:
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("invalid YouTube privacy")
    if not video.is_file() or video.stat().st_size < 500_000:
        raise FileNotFoundError("validated final.mp4 is required before upload")
    youtube = build("youtube", "v3", credentials=credentials_from_environment(), cache_discovery=False)
    request = youtube.videos().insert(
        part="snippet,status",
        body={"snippet": {"title": job["title"], "description": job["description"],
                          "categoryId": "24", "defaultLanguage": "en"},
              "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}},
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024,
                                   resumable=True),
    )
    response = execute_resumable(request)
    video_id = response["id"]
    return {"status": "success", "job_id": job["job_id"], "youtube_video_id": video_id,
            "watch_url": f"https://www.youtube.com/watch?v={video_id}",
            "privacy_status": privacy}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    job = validate_job(json.loads(args.job.read_text(encoding="utf-8")))
    result = upload(args.video, job, args.privacy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(result["watch_url"])


if __name__ == "__main__":
    main()
