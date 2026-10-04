from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .cards import generate as generate_cards
from .editor import edit
from .job import first_hook, validate_job
from .media_manager import prepare
from .scene_builder import build
from .subtitles import generate as generate_subtitles
from .tts import generate as generate_voice
from .validator import validate

ROOT = Path(__file__).resolve().parents[1]


def _notice(message: str) -> None:
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat:
        return
    try:
        from bot.notify import send
        send(message, chat)
    except Exception:
        pass  # A notification outage must not corrupt a valid render.


def run(job_path: Path, *, no_upload: bool = True, offline_test_tone: bool = False) -> dict:
    if not no_upload:
        raise ValueError("direct upload is disabled; use the reserved GitHub Actions upload workflow")
    job = validate_job(json.loads(job_path.read_text(encoding="utf-8")))
    if offline_test_tone and not no_upload:
        raise ValueError("offline test tone can only be used with --no-upload")
    output = ROOT / "output" / job["job_id"]
    output.mkdir(parents=True, exist_ok=True)
    status_path = output / "status.json"
    stage = "voice"
    try:
        _notice(f"🎙 Voice generation started\nJob ID: {job['job_id']}")
        timings, seconds = generate_voice(job, output, offline_test_tone=offline_test_tone)
        if not 5 <= seconds <= 179:
            raise ValueError(f"voice length {seconds:.1f}s is not suitable for a Short")
        hook = first_hook(job["script"])
        stage = "media"
        _notice(f"🖼 Media preparation started\nJob ID: {job['job_id']}")
        media, errors = prepare(ROOT, job, output)
        cards = generate_cards(job["person"], hook, output / "cards")
        stage = "scenes"
        scenes = build(cards, media, seconds + 0.55, output)
        generate_subtitles(timings, output, "", seconds)
        stage = "render"
        _notice(f"✂️ Editing started\nJob ID: {job['job_id']}")
        video = edit(ROOT, job, scenes, timings, seconds, output, hook)
        stage = "validate"
        report = validate(video)
        summary = {"job_id": job["job_id"], "content_hash": job["content_hash"],
                   "dedupe_key": job["dedupe_key"], "video": str(video),
                   "duration": report["duration"], "media_errors": errors,
                   "status": "rendered", "upload": None}
        status_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary
    except Exception as exc:
        status_path.write_text(json.dumps({"job_id": job["job_id"], "status": "failed",
                                           "stage": stage, "error": str(exc)[:1500]}, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        _notice(f"❌ Short failed\nJob ID: {job['job_id']}\nStage: {stage}\nError: {str(exc)[:250]}")
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--offline-test-tone", action="store_true")
    args = parser.parse_args()
    result = run(args.job, no_upload=True, offline_test_tone=args.offline_test_tone)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
