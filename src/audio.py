from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path


class OriginalAmbienceGenerator:
    """Creates a quiet original drone so the fallback has no licensing dependency."""

    def generate(self, destination: Path, duration: float, seed: str, sample_rate: int = 48000) -> Path:
        rng = random.Random(seed)
        destination.parent.mkdir(parents=True, exist_ok=True)
        phase = rng.random() * math.tau
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            for index in range(round(duration * sample_rate)):
                t = index / sample_rate
                drone = math.sin(math.tau * 43 * t + phase) * 0.11
                pulse = math.sin(math.tau * 0.17 * t) * math.sin(math.tau * 71 * t) * 0.025
                noise = (rng.random() * 2 - 1) * 0.018
                envelope = min(1.0, t / 1.2, max(0.0, (duration - t) / 1.0))
                value = max(-1, min(1, (drone + pulse + noise) * envelope))
                output.writeframesraw(struct.pack("<h", int(value * 32767)))
        return destination
