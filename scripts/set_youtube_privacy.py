from __future__ import annotations

import argparse
import json
from pathlib import Path

from googleapiclient.discovery import build

from scripts.upload_youtube import credentials_from_environment


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotently change a confirmed YouTube upload's privacy")
    parser.add_argument("--upload-result", type=Path, required=True)
    parser.add_argument("--privacy", choices=["private", "unlisted", "public"], required=True)
    args = parser.parse_args()
    payload = json.loads(args.upload_result.read_text(encoding="utf-8"))
    video_id = str(payload.get("youtube_video_id", ""))
    if payload.get("status") != "success" or not video_id:
        raise ValueError("upload result does not contain a confirmed YouTube video ID")
    youtube = build("youtube", "v3", credentials=credentials_from_environment(), cache_discovery=False)
    youtube.videos().update(
        part="status", body={"id": video_id, "status": {"privacyStatus": args.privacy,
                                                          "selfDeclaredMadeForKids": False}},
    ).execute()
    payload["privacy_status"] = args.privacy
    args.upload_result.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"youtube_video_id": video_id, "privacy_status": args.privacy}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
