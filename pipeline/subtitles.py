from __future__ import annotations

from pathlib import Path

from src.subtitles import SubtitleWriter


def generate(timings: list[dict], output: Path, hook: str, duration: float) -> Path:
    return SubtitleWriter().from_timings(timings, output / "captions.ass", [hook],
                                         hook_text=hook, hook_duration=min(2.0, duration / 5))
