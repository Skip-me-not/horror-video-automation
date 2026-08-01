from __future__ import annotations

import argparse
import json
import math
import random
import struct
import wave
from pathlib import Path

try:
    from scripts.common import load_config, load_json
except ModuleNotFoundError:
    from common import load_config, load_json


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
    samples = [0.0] * int(duration * sample_rate)
    events: list[dict[str, object]] = []

    for when in (5.8, 6.28, 6.76):
        if when < duration:
            add_burst(samples, sample_rate, when, 0.32, 72, 0.48, 0.28, rng)
            events.append({"type": "knock", "time": when})
    for when in (16.7, 17.35, 18.15):
        if when < duration:
            add_burst(samples, sample_rate, when, 0.22, 49, 0.30, 0.05, rng)
            add_burst(samples, sample_rate, when + 0.18, 0.16, 55, 0.22, 0.04, rng)
            events.append({"type": "heartbeat", "time": when})
    sting_at = max(0.0, duration - 2.7)
    add_burst(samples, sample_rate, sting_at, 1.5, 42, 0.42, 0.16, rng)
    add_burst(samples, sample_rate, sting_at, 1.1, 390, 0.08, 0.30, rng)
    events.append({"type": "sting", "time": sting_at})

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
    return {"file": str(destination), "duration_seconds": duration, "events": events}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", default="output/job.json")
    parser.add_argument("--config", default="config/default.json")
    parser.add_argument("--output", default="output/horror-sfx.wav")
    args = parser.parse_args()
    job = load_json(args.job)
    config = load_config(args.config)
    report = generate_sfx(job["job_id"], float(config["video_duration_seconds"]), Path(args.output))
    report_path = Path(args.output).with_name("sfx-report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
