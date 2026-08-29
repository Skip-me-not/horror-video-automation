from __future__ import annotations

import re
from pathlib import Path

from .utils import run


def detect_silences(path: Path, ffmpeg: str = "ffmpeg", noise_db: int = -38,
                    minimum_duration: float = 0.45) -> list[dict[str, float]]:
    result = run([ffmpeg, "-hide_banner", "-i", str(path), "-af",
                  f"silencedetect=noise={noise_db}dB:d={minimum_duration}", "-f", "null", "-"], check=False)
    starts = [float(value) for value in re.findall(r"silence_start: ([0-9.]+)", result.stderr)]
    ends = [float(value) for value in re.findall(r"silence_end: ([0-9.]+)", result.stderr)]
    return [{"start": start, "end": end} for start, end in zip(starts, ends) if end > start]


def nearest_boundary(value: float, silences: list[dict[str, float]], direction: str,
                     maximum_distance: float = 12.0) -> float | None:
    points = [item["end"] if direction == "forward" else item["start"] for item in silences]
    eligible = [point for point in points if (point >= value if direction == "forward" else point <= value)]
    if not eligible:
        return None
    point = min(eligible) if direction == "forward" else max(eligible)
    return point if abs(point - value) <= maximum_distance else None
