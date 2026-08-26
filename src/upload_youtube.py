from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class YouTubeAuthenticationError(RuntimeError):
    pass


def _credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    required = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise YouTubeAuthenticationError(f"missing GitHub Secrets: {', '.join(missing)}")
    credentials = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    try:
        credentials.refresh(Request())
    except Exception as exc:
        raise YouTubeAuthenticationError(f"YouTube refresh-token authentication failed: {exc}") from exc
    return credentials


def upload_video(video: Path, metadata: dict[str, Any], log_path: Path,
                 attempts: int = 4) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    credentials = _credentials()  # Authentication is attempted once; never regenerate on failure.
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    body = {
        "snippet": {
            "title": metadata["title"], "description": metadata["description"],
            "tags": metadata.get("tags", []), "categoryId": metadata.get("category_id", "24"),
        },
        "status": {"privacyStatus": metadata.get("privacy_status", "private"),
                   "selfDeclaredMadeForKids": False},
    }
    request = youtube.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024),
    )
    events: list[dict[str, Any]] = []
    response = None
    failures = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            events.append({"progress": round(status.progress(), 4) if status else None})
        except HttpError as exc:
            if exc.resp.status not in {500, 502, 503, 504} or failures >= attempts - 1:
                log_path.write_text(json.dumps(events + [{"error": str(exc)}], indent=2), encoding="utf-8")
                raise
            delay = 2 ** failures
            events.append({"transient_error": exc.resp.status, "retry_in_seconds": delay})
            failures += 1
            time.sleep(delay)
    video_id = str(response.get("id", ""))
    if not video_id:
        raise RuntimeError("YouTube upload returned no video ID")
    events.append({"youtube_video_id": video_id})
    log_path.write_text(json.dumps(events, indent=2), encoding="utf-8")
    return video_id
