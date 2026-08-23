from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class TTSError(RuntimeError):
    pass


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
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
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
        timing_path.write_text(json.dumps(boundaries, indent=2), encoding="utf-8")
        return boundaries

    def synthesize(self, text: str, audio_path: Path, timing_path: Path) -> list[dict[str, Any]]:
        return asyncio.run(self._synthesize(text, audio_path, timing_path))
