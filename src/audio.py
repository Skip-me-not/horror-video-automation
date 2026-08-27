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
    """Creates a copyright-safe cinematic tension arc with spatialized game cues."""

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
                # Unequal stereo drones feel wider than a centered sine wave.
                left = math.sin(math.tau * 36.5 * t + phase) * 0.055
                right = math.sin(math.tau * 38.2 * t + phase * 0.73) * 0.055
                left += math.sin(math.tau * 54 * t) * 0.022
                right += math.sin(math.tau * 51 * t) * 0.022
                noise = (rng.random() * 2 - 1)
                left += noise * 0.010
                right -= noise * 0.008
                # A fast opening impact makes the first frame audible before a swipe.
                if t < 0.38:
                    envelope = 1 - t / 0.38
                    hit = math.sin(math.tau * (92 - 55 * t) * t) * 0.48 * envelope
                    left += hit
                    right += hit * 0.92
                progress = max(0.0, min(1.0, (t - countdown_start) / max(0.1, reveal_at - countdown_start)))
                heartbeat_interval = 1.22 - 0.58 * progress
                heartbeat_phase = (t - countdown_start if t >= countdown_start else t) % heartbeat_interval
                if heartbeat_phase < 0.105:
                    beat = math.sin(math.tau * 62 * heartbeat_phase) * (0.22 + progress * 0.14)
                    beat *= 1 - heartbeat_phase / 0.105
                    left += beat
                    right += beat
                # Filterless noise riser: quiet early, urgent immediately before reveal.
                if countdown_start <= t < reveal_at:
                    riser = noise * (0.012 + progress * progress * 0.075)
                    whine = math.sin(math.tau * (220 + 520 * progress) * t) * (0.006 + 0.018 * progress)
                    left += riser + whine
                    right += riser - whine
                for tick in range(countdown_seconds):
                    tick_time = countdown_start + tick
                    distance = t - tick_time
                    if 0 <= distance < 0.055:
                        tick_value = math.sin(math.tau * 1350 * distance) * (0.38 * (1 - distance / 0.055))
                        left += tick_value
                        right += tick_value
                distance = t - reveal_at
                if 0 <= distance < 0.8:
                    impact = math.sin(math.tau * (76 - 28 * distance) * distance) * (0.62 * (1 - distance / 0.8))
                    crack = noise * 0.16 * max(0, 1 - distance / 0.14) if distance < 0.14 else 0
                    left += impact + crack
                    right += impact - crack * 0.5
                # Fade the final half-second so replaying reconnects cleanly to the opening hit.
                if duration - t < 0.5:
                    fade = max(0.0, (duration - t) / 0.5)
                    left *= fade
                    right *= fade
                left_sample = int(max(-1, min(1, left)) * 32767)
                right_sample = int(max(-1, min(1, right)) * 32767)
                frame = struct.pack("<hh", left_sample, right_sample)
                output.writeframesraw(frame)
        return destination
