from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tts import EdgeTTSNarrator, audio_duration


def synthesize(text: str, destination: Path, timing_path: Path, voice: str, rate: str) -> tuple[list[dict[str, Any]], float]:
    timings = EdgeTTSNarrator(voice, rate).synthesize(text, destination, timing_path, attempts=3)
    duration = audio_duration(destination)
    if duration <= 0 or destination.stat().st_size < 1000:
        raise RuntimeError("narration audio is empty")
    return timings, duration
