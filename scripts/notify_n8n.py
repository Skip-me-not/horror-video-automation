from __future__ import annotations

import argparse
import json
import os
from typing import Any

import requests

try:
    from scripts.common import load_json
except ModuleNotFoundError:  # Support direct script execution.
    from common import load_json


def build_callback_payload(job_id: str, status: str, result: dict[str, Any] | None,
                           error: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"job_id": job_id, "status": status}
    if result:
        payload.update({
            key: result[key] for key in (
                "youtube_video_id", "watch_url", "studio_url", "privacy_status"
            ) if key in result
        })
    if error:
        payload["error"] = error[:1000]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--status", choices=["success", "failure"], required=True)
    parser.add_argument("--result")
    parser.add_argument("--error", default="")
    args = parser.parse_args()
    job = load_json(args.job)
    url = os.getenv("N8N_CALLBACK_URL") or job.get("callback_url", "")
    if not url:
        print("Callback not configured; skipping")
        return 0
    result = load_json(args.result) if args.result else None
    payload = build_callback_payload(job["job_id"], args.status, result, args.error)
    response = requests.post(url, json=payload, timeout=20)
    response.raise_for_status()
    print(f"Callback delivered for job {job['job_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
