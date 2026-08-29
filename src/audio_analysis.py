from __future__ import annotations

import re
from pathlib import Path

from .utils import run


def energy_changes(path: Path, ffmpeg: str = "ffmpeg") -> list[dict[str, float]]:
    result = run([ffmpeg, "-hide_banner", "-i", str(path), "-filter_complex",
                  "ebur128=framelog=verbose", "-f", "null", "-"], check=False)
    readings: list[tuple[float, float]] = []
    for timestamp, loudness in re.findall(r"t:\s*([0-9.]+).*?M:\s*(-?[0-9.]+)", result.stderr):
        readings.append((float(timestamp), float(loudness)))
    changes: list[dict[str, float]] = []
    for previous, current in zip(readings, readings[1:]):
        delta = current[1] - previous[1]
        if abs(delta) >= 5.0:
            changes.append({"time": current[0], "delta_db": round(delta, 2)})
    return changes
