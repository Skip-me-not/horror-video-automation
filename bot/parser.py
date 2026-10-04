from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any

from pipeline.job import validate_job

ALIASES = {
    "PERSON": "person", "NAME": "person", "နာမည်": "person", "လူ": "person",
    "SCRIPT": "script", "စာသား": "script", "ဇာတ်ညွှန်း": "script",
    "TITLE": "title", "ခေါင်းစဉ်": "title",
    "STYLE": "style", "စတိုင်": "style",
    "VOICE": "voice", "အသံ": "voice",
    "DURATION": "duration", "ကြာချိန်": "duration",
    "MEDIA": "media", "ဗီဒီယို": "media", "မီဒီယာ": "media",
    "UPLOAD": "upload", "တင်ရန်": "upload",
    "PRIVACY": "privacy", "မြင်နိုင်မှု": "privacy",
    "FORCE": "force", "ထပ်တင်": "force",
}


def parse_short(text: str) -> dict[str, Any]:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or not re.match(r"^/short(?:@\w+)?(?:\s|$)", lines[0].strip(), re.I):
        raise ValueError("Message must start with /short")
    fields: dict[str, str] = {}
    current: str | None = None
    for line in lines[1:]:
        match = re.match(r"^\s*([^:：]{1,30})\s*[:：]\s*(.*)$", line)
        key = ALIASES.get(match.group(1).strip().upper()) if match else None
        if key:
            if key in fields:
                raise ValueError(f"Duplicate field: {key}")
            current = key
            fields[key] = match.group(2).strip()
        elif current:
            fields[current] += "\n" + line
        elif line.strip():
            raise ValueError("Put instructions under a named field such as PERSON: or SCRIPT:")
    payload = {key: value.strip() for key, value in fields.items()}
    payload["job_id"] = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + secrets.token_hex(3)
    return validate_job(payload)
