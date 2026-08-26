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


class InteractiveAudioGenerator:
    """Creates original ambience, countdown ticks, heartbeat, and reveal impact."""

    def generate(self, destination: Path, duration: float, countdown_start: float,
                 countdown_seconds: int, reveal_at: float, seed: str,
                 sample_rate: int = 48000) -> Path:
        rng = random.Random(seed)
        destination.parent.mkdir(parents=True, exist_ok=True)
        phase = rng.random() * math.tau
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            for index in range(round(duration * sample_rate)):
                t = index / sample_rate
                value = math.sin(math.tau * 38 * t + phase) * 0.065
                value += math.sin(math.tau * 57 * t) * 0.025
                value += (rng.random() * 2 - 1) * 0.012
                heartbeat_phase = t % 1.45
                if heartbeat_phase < 0.10:
                    value += math.sin(math.tau * 64 * t) * (0.22 * (1 - heartbeat_phase / 0.10))
                for tick in range(countdown_seconds):
                    tick_time = countdown_start + tick
                    distance = t - tick_time
                    if 0 <= distance < 0.055:
                        value += math.sin(math.tau * 1200 * distance) * (0.35 * (1 - distance / 0.055))
                distance = t - reveal_at
                if 0 <= distance < 0.8:
                    value += math.sin(math.tau * (72 - 25 * distance) * distance) * (0.58 * (1 - distance / 0.8))
                sample = int(max(-1, min(1, value)) * 32767)
                frame = struct.pack("<hh", sample, sample)
                output.writeframesraw(frame)
        return destination
