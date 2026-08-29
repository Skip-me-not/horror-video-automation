from __future__ import annotations

from typing import Any


COMBINATIONS = (
    (("knock", "alone"), "He heard knocking every night... but he lived alone."),
    (("camera", "figure"), "The camera caught someone already inside."),
    (("footsteps", "upstairs", "alone"), "He heard footsteps upstairs. He lived alone."),
    (("shadow", "behind"), "The shadow was standing behind him."),
    (("door", "locked"), "The locked door opened by itself."),
    (("window", "face"), "A face appeared outside the window."),
)

FALLBACKS = (
    "He thought he was alone.",
    "Something was already inside the house.",
    "This is where the story gets disturbing.",
    "What happened next made him leave.",
)


def build_hook(transcript: str, matches: list[str], minimum: float = 2.0,
               maximum: float = 5.0) -> dict[str, Any]:
    lowered = transcript.casefold()
    text = next((template for terms, template in COMBINATIONS if all(term in lowered for term in terms)), None)
    if text is None:
        text = FALLBACKS[sum(ord(character) for character in transcript[:80]) % len(FALLBACKS)]
    words = text.split()
    if len(words) > 20:
        text = " ".join(words[:20])
    duration = max(minimum, min(maximum, 2.0 + len(text.split()) * 0.13))
    return {"text": text, "duration": round(duration, 2), "signals": list(dict.fromkeys(matches)),
            "method": "deterministic-template"}
