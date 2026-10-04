from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from bot.notify import send


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--failed", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    status_path = root / "output" / args.job_id / "status.json"
    if status_path.is_file():
        status = json.loads(status_path.read_text(encoding="utf-8"))
    else:
        status = {"job_id": args.job_id, "stage": "workflow", "error": "see GitHub Actions log"}
    if args.failed:
        message = (f"❌ Short failed\nJob ID: {args.job_id}\nStage: {status.get('stage', 'upload')}\n"
                   f"Error: {str(status.get('error', 'see GitHub Actions log'))[:300]}")
    elif args.render_only:
        message = f"✅ Short rendered without upload\nJob ID: {args.job_id}\nDuration: {status.get('duration', '?')}s"
    else:
        result_path = root / "output" / args.job_id / "upload-result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        job = json.loads((root / "jobs" / "private_completed" / f"{args.job_id}.json").read_text(encoding="utf-8"))
        message = (f"✅ Short uploaded\nTitle: {job['title']}\nYouTube URL: {result['watch_url']}\n"
                   f"Duration: {status.get('duration', '?')}s\nJob ID: {args.job_id}")
    send(message, os.getenv("TELEGRAM_CHAT_ID", ""))


if __name__ == "__main__":
    main()
