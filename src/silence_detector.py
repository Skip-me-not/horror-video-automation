from __future__ import annotations

import re
from pathlib import Path

from .utils import run


def detect_silences(path: Path, ffmpeg: str = "ffmpeg", noise_db: int = -38,
                    minimum_duration: float = 0.45,
                    ranges: list[tuple[float, float]] | None = None) -> list[dict[str, float]]:
    windows = ranges or [(0.0, 0.0)]
    merged: list[tuple[float, float]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((max(0.0, start), max(0.0, end)))
    silences: list[dict[str, float]] = []
    for offset, end in merged:
        seek = ["-ss", f"{offset:.3f}"] if offset else []
        limit = ["-t", f"{end - offset:.3f}"] if end > offset else []
        result = run([ffmpeg, "-hide_banner", *seek, "-i", str(path), *limit, "-af",
                      f"silencedetect=noise={noise_db}dB:d={minimum_duration}", "-f", "null", "-"],
                     check=False)
        starts = [float(value) + offset for value in re.findall(r"silence_start: ([0-9.]+)", result.stderr)]
        ends = [float(value) + offset for value in re.findall(r"silence_end: ([0-9.]+)", result.stderr)]
        silences.extend({"start": start, "end": finish}
                        for start, finish in zip(starts, ends) if finish > start)
    return silences


def nearest_boundary(value: float, silences: list[dict[str, float]], direction: str,
                     maximum_distance: float = 12.0) -> float | None:
    points = [item["end"] if direction == "forward" else item["start"] for item in silences]
    eligible = [point for point in points if (point >= value if direction == "forward" else point <= value)]
    if not eligible:
        return None
    point = min(eligible) if direction == "forward" else max(eligible)
    return point if abs(point - value) <= maximum_distance else None
