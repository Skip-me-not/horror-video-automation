from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.kpop_automation.audio import synthesize
from src.utils import ffprobe


def generate(job: dict[str, Any], output: Path, *, offline_test_tone: bool = False) -> tuple[list[dict], float]:
    output.mkdir(parents=True, exist_ok=True)
    path = output / "voice.mp3"
    timings_path = output / "word-timings.json"
    if offline_test_tone:
        ffmpeg = os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("FFmpeg is required for the offline test tone")
        seconds = max(6.0, len(job["script"].split()) / 2.6)
        result = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                                 "-i", "sine=frequency=330:sample_rate=48000", "-t", str(seconds), str(path)],
                                capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError(result.stderr[-1000:])
        words = job["script"].split()
        timings = [{"text": word, "offset": index * seconds / len(words),
                    "duration": seconds / len(words)} for index, word in enumerate(words)]
    else:
        timings, seconds = synthesize(job["script"], path, timings_path, job["voice"], "+5%")
    if not timings:
        phrases = job["script"].split() or [job["script"]]
        timings = [{"text": phrase, "offset": index * seconds / len(phrases),
                    "duration": seconds / len(phrases)} for index, phrase in enumerate(phrases)]
    wanted = job["duration"]
    if wanted != "automatic":
        ratio = seconds / float(wanted)
        if not 0.8 <= ratio <= 1.25:
            raise ValueError(f"DURATION {wanted}s is too different from the {seconds:.1f}s voice; revise script or duration")
        if abs(ratio - 1) > 0.02:
            ffmpeg = os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg")
            adjusted = output / "voice-adjusted.mp3"
            result = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
                                     "-af", f"atempo={ratio:.5f}", str(adjusted)],
                                    capture_output=True, text=True, check=False)
            if result.returncode:
                raise RuntimeError(result.stderr[-1000:])
            adjusted.replace(path)
            timings = [{**item, "offset": float(item["offset"]) / ratio,
                        "duration": float(item.get("duration", 0.2)) / ratio} for item in timings]
            seconds = float(ffprobe(path)["format"]["duration"])
    timings_path.write_text(json.dumps(timings, ensure_ascii=False, indent=2), encoding="utf-8")
    return timings, seconds
