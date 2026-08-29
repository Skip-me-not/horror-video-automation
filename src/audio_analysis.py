from __future__ import annotations

import re
from pathlib import Path

from .utils import run


def energy_changes(path: Path, ffmpeg: str = "ffmpeg",
                   ranges: list[tuple[float, float]] | None = None) -> list[dict[str, float]]:
    windows = ranges or [(0.0, 0.0)]
    merged: list[tuple[float, float]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((max(0.0, start), max(0.0, end)))
    readings: list[tuple[float, float]] = []
    for offset, end in merged:
        seek = ["-ss", f"{offset:.3f}"] if offset else []
        limit = ["-t", f"{end - offset:.3f}"] if end > offset else []
        analysis_filter = (
            "aresample=8000,aformat=channel_layouts=mono,asetnsamples=n=16000:p=1,"
            "astats=metadata=1:reset=1,"
            "ametadata=print:key=lavfi.astats.Overall.RMS_level"
        )
        result = run([ffmpeg, "-hide_banner", *seek, "-i", str(path), *limit,
                      "-af", analysis_filter, "-f", "null", "-"], check=False)
        matches = re.findall(
            r"pts_time:([0-9.]+).*?lavfi\.astats\.Overall\.RMS_level=(-?(?:[0-9.]+|inf))",
            result.stderr, flags=re.DOTALL,
        )
        for timestamp, loudness in matches:
            if loudness.casefold().endswith("inf"):
                continue
            readings.append((float(timestamp) + offset, float(loudness)))
    changes: list[dict[str, float]] = []
    for previous, current in zip(readings, readings[1:]):
        delta = current[1] - previous[1]
        if abs(delta) >= 5.0:
            changes.append({"time": current[0], "delta_db": round(delta, 2)})
    return changes
