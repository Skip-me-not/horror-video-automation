from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


def ensure_original_theme(path: Path, seconds: int = 62) -> Path:
    """Synthesize the project's own reusable ambience; no third-party music is copied."""
    if path.is_file() and path.stat().st_size > 100_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 22050
    chords = ((220.0, 261.63, 329.63), (196.0, 246.94, 293.66),
              (174.61, 220.0, 261.63), (196.0, 246.94, 329.63))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        for start in range(0, rate * seconds, rate):
            chunk = bytearray()
            for frame in range(start, min(start + rate, rate * seconds)):
                t = frame / rate
                chord = chords[int(t // 8) % len(chords)]
                envelope = 0.72 + 0.18 * math.sin(2 * math.pi * 0.12 * t)
                pad = sum(math.sin(2 * math.pi * frequency * t) for frequency in chord) / 3
                shimmer = math.sin(2 * math.pi * 523.25 * t) * (0.5 + 0.5 * math.sin(2 * math.pi * 0.07 * t))
                value = max(-1, min(1, envelope * (0.32 * pad + 0.06 * shimmer)))
                chunk.extend(struct.pack("<h", int(value * 32767)))
            output.writeframes(chunk)
    return path
