from __future__ import annotations

from pathlib import Path


def upload_video(video: Path, job: dict[str, object], project: Path, privacy: str = "public") -> dict[str, object]:
    # The mature resumable uploader remains the single implementation of OAuth and retry logic.
    from scripts.upload_youtube import upload
    return upload(video, job, project, privacy)
