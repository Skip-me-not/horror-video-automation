from __future__ import annotations

import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .utils import write_json


class PerformanceTracker:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.stages: dict[str, float] = {}
        self.metrics: dict[str, Any] = {
            "full_video_downloaded": False,
            "audio_only_analysis": False,
            "range_video_download": False,
            "ffmpeg_full_encodes": 0,
            "ffmpeg_cache_hit": os.getenv("FFMPEG_CACHE_HIT", "unknown"),
            "yt_dlp_cache_hit": os.getenv("YTDLP_CACHE_HIT", "python-pip"),
            "pip_cache_hit": os.getenv("PIP_CACHE_HIT", "unknown"),
        }

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = round(self.stages.get(name, 0.0) + time.perf_counter() - started, 3)

    def set(self, **values: Any) -> None:
        self.metrics.update(values)

    def write(self, path: Path) -> dict[str, Any]:
        payload = {"stages_seconds": self.stages,
                   "total_seconds": round(time.perf_counter() - self.started, 3), **self.metrics}
        write_json(path, payload)
        return payload


def disk_status(path: Path, warning_gb: float, abort_gb: float, *, before_download: bool) -> dict[str, float]:
    usage = shutil.disk_usage(path)
    free_gb = usage.free / (1024 ** 3)
    status = {"total_gb": round(usage.total / (1024 ** 3), 2),
              "used_gb": round(usage.used / (1024 ** 3), 2), "free_gb": round(free_gb, 2)}
    if free_gb < warning_gb:
        print(f"DISK WARNING: only {free_gb:.2f} GB free")
    if before_download and free_gb < abort_gb:
        raise RuntimeError(f"disk guard aborted download below {abort_gb:.1f} GB free")
    return status


def write_optimization_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("""# Pipeline Optimization Audit

| Current behavior | Problem | Estimated impact | Fix implemented |
|---|---|---:|---|
| FFmpeg installed with apt every run | Repeated setup/network cost | HIGH | Check system/cache first; cache only tool binaries with an install fallback |
| yt-dlp upgraded every run | Repeated resolver/download work | MEDIUM | Pinned Python dependency using setup-python pip cache |
| Entire 720p podcast downloaded before selection | Hundreds of unnecessary MB | HIGH | Metadata/history, captions, audio, then selected range; full video is fallback only |
| Silence/audio work followed full video download | Expensive work starts too early | HIGH | Transcript candidates first; audio-only local scans around top candidates |
| Source transform, clip renders, concat, caption mux | Multiple full-resolution encodes | HIGH | One filter-complex render with source transform, B-roll, captions, and audio |
| B-roll downloaded before an exact slot plan | Excess API calls and media | MEDIUM | Plan exact slots first; download only unique selected queries, maximum seven |
| Repeated stock queries | Duplicate API/download cost | MEDIUM | Per-run query and asset caches with immediate provider fallback stop |
| ffprobe called independently | Repeated subprocess/decode startup | LOW | One JSON probe cached by path, size, and mtime |
| Repo temp folders used for every run | Weak cleanup and disk isolation | MEDIUM | One `$RUNNER_TEMP/horror-short` tree and disk watchdog |
| Large diagnostic artifact set retained five days | Storage/network waste | MEDIUM | Minimal three-day production artifact plus opt-in debug artifact |
| 60-minute job timeout | Hung sources consume excess minutes | MEDIUM | 45-minute job limit plus subprocess/network retry limits |
| Lightweight history committed after success | Needed for early duplicate exit | LOW | Retained; commit only when `data/history.json` changed |

No Python step loads full audio or video into RAM. Media remains file/stream based through yt-dlp,
requests streaming, FFmpeg, and chunked hashing.
""", encoding="utf-8")
