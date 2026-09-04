from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

try:
    from scripts.common import ValidationError, load_json, resolve_asset
except ModuleNotFoundError:  # Support direct script execution.
    from common import ValidationError, load_json, resolve_asset


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TRANSIENT = {429, 500, 502, 503, 504}
ALLOWED_PRIVACY = {"public"}


def shorts_title(value: str) -> str:
    suffix = " #shorts"
    cleaned = " ".join(value.split()).strip('"')

    if cleaned.casefold().endswith("#shorts"):
        return cleaned[:100]

    limit = 100 - len(suffix)

    if len(cleaned) > limit:
        shortened = (
            cleaned[: limit - 1]
            .rsplit(" ", 1)[0]
            .rstrip(".,;:!?")
        )
        cleaned = (shortened or cleaned[: limit - 1]).rstrip() + "…"

    return cleaned + suffix


def shorts_description(value: str) -> str:
    cleaned = value.strip()
    hashtags = "#Lululala #celebrity #kpop #popculture #shorts"

    return (
        cleaned
        if "#shorts" in cleaned.casefold()
        else f"{cleaned}\n\n{hashtags}".strip()
    )


def credentials_from_environment() -> Credentials:
    values = {
        name: os.getenv(name, "")
        for name in (
            "YOUTUBE_CLIENT_ID",
            "YOUTUBE_CLIENT_SECRET",
            "YOUTUBE_REFRESH_TOKEN",
        )
    }

    missing = [
        name
        for name, value in values.items()
        if not value
    ]

    if missing:
        raise ValidationError(
            f"missing YouTube secrets: {', '.join(missing)}"
        )

    return Credentials(
        token=None,
        refresh_token=values["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=values["YOUTUBE_CLIENT_ID"],
        client_secret=values["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )


def execute_resumable(request, attempts: int = 7):
    response = None
    retry = 0

    while response is None:
        try:
            _, response = request.next_chunk()

        except HttpError as exc:
            status = getattr(exc.resp, "status", 0)

            if status not in TRANSIENT or retry >= attempts:
                raise

            time.sleep(
                min(
                    64,
                    (2 ** retry) + random.random(),
                )
            )

            retry += 1

        except (OSError, TimeoutError):
            if retry >= attempts:
                raise

            time.sleep(
                min(
                    64,
                    (2 ** retry) + random.random(),
                )
            )

            retry += 1

    return response


def upload(
    video: Path,
    job: dict,
    project: Path,
    privacy: str,
) -> dict:

    if privacy not in ALLOWED_PRIVACY:
        raise ValidationError(
            "privacy must be public"
        )

    if not video.is_file():
        raise FileNotFoundError(
            f"video is missing: {video}"
        )

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials_from_environment(),
        cache_discovery=False,
    )

    body = {
        "snippet": {
            "title": shorts_title(job["title"]),
            "description": shorts_description(job["description"]),
            "tags": job["tags"],
            "categoryId": "24",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(
            str(video),
            mimetype="video/mp4",
            chunksize=8 * 1024 * 1024,
            resumable=True,
        ),
    )

    response = execute_resumable(request)
    video_id = response["id"]

    thumbnail = job.get("thumbnail_file", "")

    if thumbnail:
        thumb_path = resolve_asset(
            project / "assets/thumbnails",
            thumbnail,
        )

        if not thumb_path.is_file():
            raise FileNotFoundError(
                f"thumbnail is missing: {thumb_path}"
            )

        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(
                str(thumb_path),
                resumable=True,
            ),
        ).execute()

    return {
        "status": "success",
        "job_id": job["job_id"],
        "youtube_video_id": video_id,
        "watch_url": f"https://www.youtube.com/watch?v={video_id}",
        "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
        "privacy_status": privacy,
    }


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--job",
        required=True,
    )

    parser.add_argument(
        "--video",
        required=True,
    )

    parser.add_argument(
        "--privacy",
        choices=["public"],
        default="public",
    )

    parser.add_argument(
        "--output",
        default="output/upload-result.json",
    )

    args = parser.parse_args()

    project = Path(__file__).resolve().parents[1]

    result = upload(
        Path(args.video),
        load_json(args.job),
        project,
        args.privacy,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(result, indent=2)
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
