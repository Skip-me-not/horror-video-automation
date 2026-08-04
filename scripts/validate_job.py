from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.common import SAFE_JOB_ID, ValidationError, load_config, load_json, safe_filename
except ModuleNotFoundError:  # Support `python scripts/validate_job.py`.
    from common import SAFE_JOB_ID, ValidationError, load_config, load_json, safe_filename


REQUIRED = {"job_id", "title", "story", "description", "tags", "background_file"}

ALLOWED = REQUIRED | {
    "ambience_file",
    "thumbnail_file",
    "privacy_status",
    "callback_url",
    "background_query",
    "watermark_text",
}

ALLOWED_PRIVACY = {"private", "unlisted", "public"}


def decode_payload(encoded: str, max_bytes: int) -> dict[str, Any]:
    if len(encoded) > ((max_bytes + 2) // 3) * 4 + 8:
        raise ValidationError("encoded workflow payload is too large")

    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValidationError("payload is not valid base64") from exc

    if len(raw) > max_bytes:
        raise ValidationError("decoded workflow payload is too large")

    try:
        job = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("payload is not valid UTF-8 JSON") from exc

    if not isinstance(job, dict):
        raise ValidationError("payload must be a JSON object")

    return job


def validate_job(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    missing = REQUIRED - job.keys()
    unknown = job.keys() - ALLOWED

    if missing:
        raise ValidationError(f"missing fields: {', '.join(sorted(missing))}")

    if unknown:
        raise ValidationError(f"unknown fields: {', '.join(sorted(unknown))}")

    if not isinstance(job["job_id"], str) or not SAFE_JOB_ID.fullmatch(job["job_id"]):
        raise ValidationError(
            "job_id must use only letters, digits, underscore, and hyphen"
        )

    if not isinstance(job["title"], str) or not 1 <= len(job["title"].strip()) <= 100:
        raise ValidationError("title must contain 1 to 100 characters")

    story = job["story"]

    if not isinstance(story, str):
        raise ValidationError("story must be text")

    length = len(story.strip())

    if not int(config["min_story_characters"]) <= length <= int(
        config["max_story_characters"]
    ):
        raise ValidationError(
            f"story must contain {config['min_story_characters']} to "
            f"{config['max_story_characters']} characters"
        )

    if not isinstance(job["description"], str) or len(job["description"]) > 5000:
        raise ValidationError("description must be text up to 5000 characters")

    tags = job["tags"]

    if (
        not isinstance(tags, list)
        or len(tags) > 30
        or any(
            not isinstance(tag, str) or not 1 <= len(tag) <= 100
            for tag in tags
        )
        or sum(len(tag) for tag in tags) > 450
    ):
        raise ValidationError(
            "tags must be up to 30 short strings (450 characters total)"
        )

    safe_filename(job["background_file"], "background_file")

    safe_filename(
        job.get("ambience_file", ""),
        "ambience_file",
        allow_empty=True,
    )

    safe_filename(
        job.get("thumbnail_file", ""),
        "thumbnail_file",
        allow_empty=True,
    )

    privacy = job.get(
        "privacy_status",
        config["default_privacy_status"],
    )

    if privacy not in ALLOWED_PRIVACY:
        raise ValidationError(
            "privacy_status must be private, unlisted, or public"
        )

    callback = job.get("callback_url", "")

    if not isinstance(callback, str):
        raise ValidationError("callback_url must be text")

    if callback and not (
        len(callback) <= 2048
        and callback.startswith("https://")
    ):
        raise ValidationError("callback_url must be an HTTPS URL")

    background_query = job.get(
        "background_query",
        config["pexels_default_query"],
    )

    if (
        not isinstance(background_query, str)
        or not 3 <= len(background_query.strip()) <= 80
        or any(ord(char) < 32 for char in background_query)
    ):
        raise ValidationError(
            "background_query must contain 3 to 80 printable characters"
        )

    unsafe_subjects = {
        "person",
        "people",
        "man",
        "woman",
        "child",
        "face",
        "portrait",
    }

    if unsafe_subjects.intersection(
        background_query.lower().replace("-", " ").split()
    ):
        raise ValidationError(
            "background_query must request an empty environment without people"
        )

    watermark_text = job.get(
        "watermark_text",
        config["watermark_text"],
    )

    if (
        not isinstance(watermark_text, str)
        or not 1 <= len(watermark_text.strip()) <= 32
        or any(
            char not in
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789 @_'!-"
            for char in watermark_text
        )
    ):
        raise ValidationError(
            "watermark_text contains unsupported characters"
        )

    normalized = dict(job)

    normalized.update(
        ambience_file=job.get("ambience_file", ""),
        thumbnail_file=job.get("thumbnail_file", ""),
        privacy_status=privacy,
        callback_url=callback,
        background_query=background_query.strip(),
        watermark_text=watermark_text.strip(),
    )

    return normalized


def main() -> int:
    parser = argparse.ArgumentParser()

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument("--job")
    group.add_argument("--payload")

    parser.add_argument(
        "--config",
        default="config/default.json",
    )

    parser.add_argument(
        "--output",
        default="output/job.json",
    )

    parser.add_argument(
        "--expected-job-id",
    )

    args = parser.parse_args()

    try:
        config = load_config(args.config)

        job = (
            load_json(args.job)
            if args.job
            else decode_payload(
                args.payload,
                int(config["max_payload_bytes"]),
            )
        )

        normalized = validate_job(job, config)

        if (
            args.expected_job_id
            and normalized["job_id"] != args.expected_job_id
        ):
            raise ValidationError(
                "payload job_id does not match workflow job_id"
            )

        output = Path(args.output)

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output.write_text(
            json.dumps(
                normalized,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(
            f"Validated job {normalized['job_id']} "
            f"({len(normalized['story'])} characters)"
        )

        return 0

    except (ValidationError, OSError) as exc:
        print(
            f"Validation failed: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
