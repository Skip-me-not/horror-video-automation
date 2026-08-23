from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.common import SAFE_JOB_ID, ValidationError
except ModuleNotFoundError:
    from common import SAFE_JOB_ID, ValidationError


def load_bank(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path} is not valid JSON") from exc


def select_idea(bank: Any, idea_number: int) -> dict[str, Any]:
    if not isinstance(bank, list) or not bank:
        raise ValidationError("idea bank must be a non-empty JSON array")
    if not 1 <= idea_number <= len(bank):
        raise ValidationError(f"idea_number must be between 1 and {len(bank)}")
    idea = bank[idea_number - 1]
    if not isinstance(idea, dict):
        raise ValidationError("fact bank entry must be an object")
    if idea.get("id") != f"HF{idea_number:04d}" or idea.get("content_type") != "sourced_horror_fact":
        raise ValidationError("fact bank order, ID, or content type is invalid")
    return idea


def build_job(idea: dict[str, Any], job_id: str) -> dict[str, Any]:
    if not SAFE_JOB_ID.fullmatch(job_id):
        raise ValidationError("job_id must use only letters, digits, underscore, and hyphen")
    job = {
        "title": idea["title"], "story": idea["script"],
        "description": f"Source: {idea['source_url']}\n{idea['verification_note']}",
        "tags": ["horror facts", str(idea["evidence_type"]).replace("_", " "), "shorts"],
        "background_file": "dark-corridor.png",
        "background_query": f"{idea['source_date']} {idea['location']} archival horror",
        "background_queries": [f"{idea['source_date']} {idea['location']} archival horror folklore"],
        "genre": idea["category"], "watermark_text": "", "ambience_file": "", "thumbnail_file": "",
    }
    job.update(job_id=job_id, privacy_status="public", callback_url="")
    return job


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one video job from the numbered idea bank.")
    parser.add_argument("--bank", default="data/script_bank.json")
    parser.add_argument("--idea-number", type=int, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output", default="output/idea-job.json")
    args = parser.parse_args()
    try:
        idea = select_idea(load_bank(args.bank), args.idea_number)
        job = build_job(idea, args.job_id)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(job, indent=2), encoding="utf-8")
        print(f"Selected sourced fact {args.idea_number}: {job['title']}")
        return 0
    except (ValidationError, OSError) as exc:
        print(f"Idea selection failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
