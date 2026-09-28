from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .job import validate_job

ROOT = Path(__file__).resolve().parents[1]


def reserve(job: dict) -> Path:
    key = job["dedupe_key"]
    lock = ROOT / "jobs" / "locks" / f"{key}.json"
    receipt = ROOT / "jobs" / "completed" / f"{key}.json"
    if lock.exists() or receipt.exists():
        raise ValueError("job was already reserved or uploaded; no duplicate upload attempted")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"job_id": job["job_id"], "dedupe_key": key,
                                "reserved_at": datetime.now(timezone.utc).isoformat()}, indent=2),
                    encoding="utf-8")
    return lock


def complete(job: dict, result: dict) -> Path:
    key = job["dedupe_key"]
    lock = ROOT / "jobs" / "locks" / f"{key}.json"
    if not lock.is_file():
        raise ValueError("job reservation is missing")
    if result.get("status") != "success" or not result.get("youtube_video_id"):
        raise ValueError("confirmed YouTube result is required")
    receipt = ROOT / "jobs" / "completed" / f"{key}.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"job_id": job["job_id"], "content_hash": job["content_hash"],
                                   "youtube_video_id": result["youtube_video_id"],
                                   "privacy_status": result["privacy_status"],
                                   "recorded_at": datetime.now(timezone.utc).isoformat()}, indent=2),
                       encoding="utf-8")
    lock.unlink()
    return receipt


def archive(job: dict, folder: str) -> Path:
    pending = ROOT / "jobs" / "pending" / f"{job['job_id']}.json"
    destination = ROOT / "jobs" / folder / pending.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if pending.is_file():
        pending.replace(destination)
    return destination


def visible(job: dict, result: dict) -> Path:
    receipt = ROOT / "jobs" / "completed" / f"{job['dedupe_key']}.json"
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    if payload["youtube_video_id"] != result.get("youtube_video_id"):
        raise ValueError("YouTube ID changed after reservation")
    payload["privacy_status"] = result["privacy_status"]
    receipt.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["reserve", "complete", "visible", "archive", "fail"])
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    job = validate_job(json.loads(args.job.read_text(encoding="utf-8")))
    if args.action == "reserve":
        path = reserve(job)
    elif args.action in {"complete", "visible"}:
        if not args.result:
            raise ValueError("--result is required")
        result = json.loads(args.result.read_text(encoding="utf-8"))
        path = complete(job, result) if args.action == "complete" else visible(job, result)
    else:
        path = archive(job, "private_completed" if args.action == "archive" else "failed")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
