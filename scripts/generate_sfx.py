from __future__ import annotations

import argparse
import json
import math
import random
import struct
import wave
from pathlib import Path

try:
    from scripts.common import effective_video_duration, load_config, load_json
except ModuleNotFoundError:
    from common import effective_video_duration, load_config, load_json


def add_burst(samples: list[float], sample_rate: int, start: float, length: float,
              frequency: float, gain: float, noise: float, rng: random.Random) -> None:
    first = max(0, int(start * sample_rate))
    count = min(int(length * sample_rate), len(samples) - first)
    for offset in range(max(0, count)):
        t = offset / sample_rate
        envelope = math.exp(-7.5 * t / max(length, 0.01))
        tone = math.sin(2 * math.pi * frequency * t)
        grit = rng.uniform(-1.0, 1.0) * noise
        samples[first + offset] += gain * envelope * (tone + grit)


def generate_sfx(job_id: str, duration: float, destination: Path,
                 sample_rate: int = 48000) -> dict[str, object]:
    rng = random.Random(job_id)
    sample_count = int(duration * sample_rate)
    samples = [0.0] * sample_count
    events: list[dict[str, object]] = []

    # A continuous original horror bed: sub-bass beating, cold air, and an
    # unstable distant tone. It is deterministic and requires no licensed audio.
    for index in range(sample_count):
        t = index / sample_rate
        slow_breath = 0.55 + 0.45 * math.sin(2 * math.pi * 0.075 * t - 0.8)
        drone = (
            0.105 * math.sin(2 * math.pi * 37.0 * t)
            + 0.075 * math.sin(2 * math.pi * 40.4 * t)
            + 0.035 * math.sin(2 * math.pi * 73.5 * t)
        )
        distant_frequency = 176.0 + 7.0 * math.sin(2 * math.pi * 0.043 * t)
        distant = 0.028 * math.sin(2 * math.pi * distant_frequency * t)
        wind = rng.uniform(-1.0, 1.0) * 0.026 * slow_breath
        samples[index] = drone * (0.72 + 0.28 * slow_breath) + distant * slow_breath + wind

    for when in (duration * 0.19, duration * 0.21, duration * 0.23):
        if when < duration:
            add_burst(samples, sample_rate, when, 0.32, 72, 0.48, 0.28, rng)
            events.append({"type": "knock", "time": when})
    for when in (duration * 0.55, duration * 0.58, duration * 0.61):
        if when < duration:
            add_burst(samples, sample_rate, when, 0.22, 49, 0.30, 0.05, rng)
            add_burst(samples, sample_rate, when + 0.18, 0.16, 55, 0.22, 0.04, rng)
            events.append({"type": "heartbeat", "time": when})
    sting_at = max(0.0, duration - 2.7)
    add_burst(samples, sample_rate, sting_at, 1.5, 42, 0.42, 0.16, rng)
    add_burst(samples, sample_rate, sting_at, 1.1, 390, 0.08, 0.30, rng)
    events.append({"type": "sting", "time": sting_at})

    for when in [duration * fraction for fraction in (0.36, 0.72)]:
        if when < duration:
            add_burst(samples, sample_rate, when, 2.4, 118, 0.10, 0.12, rng)
            events.append({"type": "distant_swell", "time": when})

    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for value in samples:
            clipped = max(-1.0, min(1.0, value))
            frames.extend(struct.pack("<h", round(clipped * 32767)))
        handle.writeframes(frames)
    return {
        "file": str(destination),
        "duration_seconds": duration,
        "continuous_layers": ["sub_bass_drone", "cold_wind", "distant_tone"],
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", default="output/job.json")
    parser.add_argument("--config", default="config/default.json")
    parser.add_argument("--output", default="output/horror-sfx.wav")
    args = parser.parse_args()
    job = load_json(args.job)
    config = load_config(args.config)
    voice_report = load_json(Path(config["output_directory"]) / "voice-report.json")
    duration = effective_video_duration(float(voice_report["duration_seconds"]), config, job["job_id"])
    report = generate_sfx(job["job_id"], duration, Path(args.output))
    report_path = Path(args.output).with_name("sfx-report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
