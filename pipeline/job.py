from __future__ import annotations

import hashlib
import re
from typing import Any

JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
VOICE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z0-9]+Neural$")


def validate_job(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("job must be a JSON object")
    person = str(value.get("person", "")).strip()
    script = str(value.get("script", "")).strip()
    if not 2 <= len(person) <= 100 or any(ord(ch) < 32 for ch in person):
        raise ValueError("PERSON must be 2–100 printable characters")
    if not 20 <= len(script) <= 6000:
        raise ValueError("SCRIPT must be 20–6000 characters")
    job_id = str(value.get("job_id", "")).strip()
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("invalid job_id")
    title = str(value.get("title") or f"{person} — Latest Short Update").strip()
    if not 1 <= len(title) <= 100 or "\n" in title:
        raise ValueError("TITLE must be 1–100 characters on one line")
    style = str(value.get("style") or "fast_celeb").strip()
    if style != "fast_celeb":
        raise ValueError("unsupported STYLE; available: fast_celeb")
    voice = str(value.get("voice") or "en-US-AriaNeural").strip()
    if not VOICE.fullmatch(voice):
        raise ValueError("VOICE must be an Edge TTS Neural voice name")
    duration_raw = value.get("duration") or "automatic"
    duration: int | str
    if str(duration_raw).casefold() == "automatic":
        duration = "automatic"
    else:
        try:
            duration = int(duration_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("DURATION must be automatic or an integer from 10 to 180") from exc
        if not 10 <= duration <= 180:
            raise ValueError("DURATION must be 10–180 seconds")
    media = str(value.get("media") or "automatic").strip()
    if len(media) > 2048 or not media:
        raise ValueError("MEDIA instruction is too long")
    upload = str(value.get("upload") or "youtube").casefold()
    if upload not in {"youtube", "none"}:
        raise ValueError("UPLOAD must be youtube or none")
    privacy = str(value.get("privacy") or "private").casefold()
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("PRIVACY must be private, unlisted, or public")
    force = str(value.get("force", "false")).casefold() in {"true", "yes", "1"}
    digest = hashlib.sha256((person.casefold() + "\n" + script).encode("utf-8")).hexdigest()
    dedupe_key = hashlib.sha256((digest + job_id).encode()).hexdigest() if force else digest
    return {"job_id": job_id, "person": person, "title": title, "script": script,
            "style": style, "voice": voice, "duration": duration, "media": media,
            "upload": upload, "privacy": privacy, "force": force, "content_hash": digest,
            "dedupe_key": dedupe_key,
            "description": f"A Lululala Short about {person}.\n\n#shorts"}


def first_hook(script: str) -> str:
    first = re.split(r"(?<=[.!?။])\s+|\n", script.strip(), maxsplit=1)[0]
    words = first.split()
    return first if len(words) <= 12 else " ".join(words[:10]).rstrip(" ,;:") + "…"
