from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


class TTSError(RuntimeError):
    pass


def fallback_word_timings(text: str, duration: float) -> list[dict[str, Any]]:
    words = re.findall(r"\b[\w'’-]+\b", text)
    if not words or duration <= 0:
        return []
    slot = duration / len(words)
    return [
        {"text": word, "offset": round(index * slot, 3), "duration": round(slot, 3)}
        for index, word in enumerate(words)
    ]


def audio_duration(path: Path) -> float:
    try:
        from .utils import ffprobe
        return float(ffprobe(path).get("format", {}).get("duration") or 0)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise TTSError(f"could not measure narration duration: {exc}") from exc


class EdgeTTSNarrator:
    def __init__(self, voice: str, rate: str = "-8%") -> None:
        self.voice = voice
        self.rate = rate

    async def _synthesize(self, text: str, audio_path: Path, timing_path: Path) -> list[dict[str, Any]]:
        try:
            import edge_tts
        except ImportError as exc:
            raise TTSError("edge-tts is not installed; run pip install -r requirements.txt") from exc
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, boundary="WordBoundary")
        boundaries: list[dict[str, Any]] = []
        with audio_path.open("wb") as audio:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    boundaries.append({
                        "text": chunk["text"],
                        "offset": round(chunk["offset"] / 10_000_000, 3),
                        "duration": round(chunk["duration"] / 10_000_000, 3),
                    })
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise TTSError("edge-tts returned no audio")
        if not boundaries:
            boundaries = fallback_word_timings(text, audio_duration(audio_path))
        if not boundaries:
            raise TTSError("edge-tts returned no usable word timings")
        timing_path.write_text(json.dumps(boundaries, indent=2), encoding="utf-8")
        return boundaries

    def synthesize(self, text: str, audio_path: Path, timing_path: Path,
                   attempts: int = 3) -> list[dict[str, Any]]:
        """Synthesize with short retries for Edge's intermittent empty responses."""
        last_error: Exception | None = None
        for attempt in range(max(1, attempts)):
            try:
                return asyncio.run(self._synthesize(text, audio_path, timing_path))
            except Exception as exc:
                last_error = exc
                audio_path.unlink(missing_ok=True)
                timing_path.unlink(missing_ok=True)
                if attempt < attempts - 1:
                    time.sleep(2.0 * (attempt + 1))
        raise TTSError(f"Edge TTS failed after {max(1, attempts)} attempts: {last_error}") from last_error
