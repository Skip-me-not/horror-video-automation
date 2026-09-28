from __future__ import annotations

import json
import os
from pathlib import Path

from .job import JOB_ID, validate_job

ROOT = Path(__file__).resolve().parents[1]


def load_event(path: Path) -> tuple[dict, str]:
    event = json.loads(path.read_text(encoding="utf-8"))
    payload = event.get("client_payload") or {}
    raw = payload.get("job")
    if raw is None:
        raw_json = (event.get("inputs") or {}).get("job_json", "")
        if raw_json:
            raw = json.loads(raw_json)
        else:
            job_id = (event.get("inputs") or {}).get("job_id", "")
            if not JOB_ID.fullmatch(job_id or "") or not (ROOT / "jobs" / "pending" / f"{job_id}.json").is_file():
                raise ValueError("dispatch needs client_payload.job, job_json, or an existing pending job_id")
            raw = json.loads((ROOT / "jobs" / "pending" / f"{job_id}.json").read_text(encoding="utf-8"))
    job = validate_job(raw)
    chat = str(payload.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", ""))
    if chat and (not chat.lstrip("-").isdigit() or len(chat) > 20):
        raise ValueError("invalid Telegram chat ID")
    return job, chat


def main() -> None:
    job, chat = load_event(Path(os.environ["GITHUB_EVENT_PATH"]))
    destination = ROOT / "jobs" / "pending" / f"{job['job_id']}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write(f"job_id={job['job_id']}\ndedupe_key={job['dedupe_key']}\n"
                     f"upload={job['upload']}\nprivacy={job['privacy']}\n")
    if chat:
        with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as stream:
            stream.write(f"TELEGRAM_CHAT_ID={chat}\n")
    print("Validated job", job["job_id"])


if __name__ == "__main__":
    main()
