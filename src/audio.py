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
        room_left = 0.0
        room_right = 0.0
        tension_start = max(5.0, countdown_start - 25.0)
        heartbeat_start = max(tension_start, countdown_start - 17.0)
        metallic_cues = (6.2, 18.5, 30.0, max(34.0, countdown_start - 5.5))
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            for index in range(round(duration * sample_rate)):
                t = index / sample_rate
                # Low, detuned room tone. Keeping the partials quiet and unequal
                # makes the bed feel cinematic instead of like a raw test tone.
                breath = 0.72 + 0.28 * math.sin(math.tau * 0.035 * t + phase)
                left = math.sin(math.tau * 31.4 * t + phase) * 0.027 * breath
                right = math.sin(math.tau * 32.1 * t + phase * 0.71) * 0.027 * breath
                left += math.sin(math.tau * 47.2 * t + math.sin(t * 0.11)) * 0.014
                right += math.sin(math.tau * 45.8 * t - math.sin(t * 0.09)) * 0.014

                # Heavily smoothed noise resembles air moving through a distant
                # room; it removes the harsh white hiss from the previous mix.
                room_left = room_left * 0.9965 + (rng.random() * 2 - 1) * 0.0035
                room_right = room_right * 0.9962 + (rng.random() * 2 - 1) * 0.0038
                left += room_left * 0.055
                right += room_right * 0.055

                # A short sub hit and reverse-feeling breath create an audible hook
                # without the clipping crack of the earlier opening impact.
                if t < 0.75:
                    envelope = math.sin(math.pi * min(1.0, t / 0.75))
                    hit = math.sin(math.tau * (58 - 22 * t) * t) * 0.25 * envelope
                    left += hit
                    right += hit * 0.96

                # Sparse bowed-metal resonances keep the long observation section
                # alive while leaving enough silence for tension to breathe.
                for cue_index, cue in enumerate(metallic_cues):
                    distance = t - cue
                    if 0 <= distance < 4.8:
                        decay = math.exp(-distance * 0.72)
                        frequency = 93.0 + cue_index * 14.5
                        bowed = math.sin(math.tau * frequency * distance + phase) * decay * 0.035
                        shimmer = math.sin(math.tau * (frequency * 2.01) * distance) * decay * 0.009
                        if cue_index % 2:
                            left += bowed * 0.45
                            right += bowed + shimmer
                        else:
                            left += bowed + shimmer
                            right += bowed * 0.45

                tension = max(0.0, min(1.0, (t - tension_start) / max(0.1, reveal_at - tension_start)))
                if tension > 0:
                    high = math.sin(math.tau * (146 + 58 * tension) * t + phase) * 0.006 * tension
                    left += high
                    right -= high * 0.7

                # The heartbeat enters late, then accelerates naturally toward the
                # answer. A softer second pulse gives it a recognisable lub-dub.
                heart_progress = max(0.0, min(1.0, (t - heartbeat_start) /
                                              max(0.1, reveal_at - heartbeat_start)))
                if t >= heartbeat_start and t < reveal_at:
                    heartbeat_interval = 1.18 - 0.47 * heart_progress
                    heartbeat_phase = (t - heartbeat_start) % heartbeat_interval
                    beat = 0.0
                    if heartbeat_phase < 0.085:
                        beat = math.sin(math.tau * 57 * heartbeat_phase) * (1 - heartbeat_phase / 0.085)
                    elif 0.14 <= heartbeat_phase < 0.215:
                        dub_phase = heartbeat_phase - 0.14
                        beat = math.sin(math.tau * 49 * dub_phase) * 0.62 * (1 - dub_phase / 0.075)
                    beat *= 0.12 + heart_progress * 0.10
                    left += beat
                    right += beat * 0.92

                for tick in range(countdown_seconds):
                    tick_time = countdown_start + tick
                    distance = t - tick_time
                    if 0 <= distance < 0.09:
                        tick_envelope = 1 - distance / 0.09
                        tick_value = (
                            math.sin(math.tau * 560 * distance) * 0.13
                            + math.sin(math.tau * 92 * distance) * 0.08
                        ) * tick_envelope
                        left += tick_value
                        right += tick_value * 0.94
                distance = t - reveal_at
                if 0 <= distance < 1.4:
                    impact_envelope = math.exp(-distance * 2.4)
                    impact = math.sin(math.tau * (51 - 9 * distance) * distance) * 0.42 * impact_envelope
                    burst = (room_left + room_right) * 0.28 * math.exp(-distance * 8.0)
                    left += impact + burst
                    right += impact - burst * 0.45
                aftershock = t - (reveal_at + 2.7)
                if 0 <= aftershock < 1.8:
                    tail = math.sin(math.tau * 38 * aftershock) * 0.10 * math.exp(-aftershock * 2.0)
                    left += tail
                    right += tail

                # Soft limiting keeps phone playback full without digital clipping.
                left = math.tanh(left * 1.35) / math.tanh(1.35)
                right = math.tanh(right * 1.35) / math.tanh(1.35)
                if duration - t < 0.8:
                    fade = max(0.0, (duration - t) / 0.8)
                    left *= fade
                    right *= fade
                left_sample = int(max(-1, min(1, left)) * 32767)
                right_sample = int(max(-1, min(1, right)) * 32767)
                frame = struct.pack("<hh", left_sample, right_sample)
                output.writeframesraw(frame)
        return destination
