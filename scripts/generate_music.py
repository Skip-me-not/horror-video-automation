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


def smooth_envelope(position: float, length: float, attack: float, release: float) -> float:
    return max(0.0, min(1.0, position / max(attack, 0.001),
                        (length - position) / max(release, 0.001)))


def generate_music(job_id: str, duration: float, destination: Path,
                   sample_rate: int = 48000) -> dict[str, object]:
    """Create non-melodic dread: beating sub drones, air, scrapes, and a final sting."""
    rng = random.Random(f"creepy-music:{job_id}")
    frame_count = int(duration * sample_rate)
    samples = [0.0] * frame_count
    brown = 0.0
    air = 0.0

    # Inharmonic, slightly detuned tones never resolve into a musical chord.
    frequencies = (
        27.31 + rng.uniform(-0.18, 0.18),
        28.07 + rng.uniform(-0.18, 0.18),
        41.17 + rng.uniform(-0.25, 0.25),
        57.83 + rng.uniform(-0.30, 0.30),
    )
    for index in range(frame_count):
        t = index / sample_rate
        progress = min(1.0, t / max(duration, 0.001))
        fade = smooth_envelope(t, duration, 2.4, 2.0)
        noise = rng.uniform(-1.0, 1.0)
        brown = brown * 0.9965 + noise * 0.0035
        previous_air = air
        air = air * 0.91 + noise * 0.09
        breath = air - previous_air
        beating_drone = (
            math.sin(2 * math.pi * frequencies[0] * t)
            + 0.82 * math.sin(2 * math.pi * frequencies[1] * t)
            + 0.34 * math.sin(2 * math.pi * frequencies[2] * t + 1.7)
            + 0.20 * math.sin(2 * math.pi * frequencies[3] * t + 0.4)
        )
        slow_unease = 0.74 + 0.26 * math.sin(2 * math.pi * 0.071 * t + 0.9)
        samples[index] = fade * (
            beating_drone * (0.036 + 0.020 * progress) * slow_unease
            + brown * 0.34
            + breath * 0.025
        )

    # Long, irregular metallic swells resemble stressed pipes or distant scraping.
    scrape_events: list[dict[str, float]] = []
    cursor = rng.uniform(4.0, 7.0)
    while cursor < duration - 2.0:
        length = rng.uniform(2.8, 5.8)
        base = rng.uniform(145.0, 285.0)
        end = min(duration, cursor + length)
        for index in range(int(cursor * sample_rate), int(end * sample_rate)):
            t = index / sample_rate - cursor
            envelope = smooth_envelope(t, end - cursor, 1.4, 1.8)
            glide = base * (1.0 + 0.12 * t / max(length, 0.001))
            scrape = (
                math.sin(2 * math.pi * glide * t)
                + 0.52 * math.sin(2 * math.pi * glide * 1.417 * t + 0.6)
                + 0.23 * math.sin(2 * math.pi * glide * 2.071 * t)
            )
            samples[index] += scrape * envelope * 0.022
        scrape_events.append({"time": round(cursor, 3), "duration": round(end - cursor, 3)})
        cursor += rng.uniform(7.5, 14.0)

    # A tightening sub pulse raises tension near the end without becoming a beat.
    pulse_events: list[float] = []
    cursor = max(2.0, duration * 0.58)
    interval = 2.6
    while cursor < duration - 0.7:
        end = min(duration, cursor + 1.15)
        for index in range(int(cursor * sample_rate), int(end * sample_rate)):
            t = index / sample_rate - cursor
            envelope = math.exp(-3.4 * t)
            samples[index] += 0.105 * envelope * math.sin(2 * math.pi * 34.1 * t)
        pulse_events.append(round(cursor, 3))
        cursor += interval
        interval = max(1.15, interval * 0.88)

    # Final low impact and dissonant tail create a disturbing cutoff.
    sting_start = max(0.0, duration - 1.8)
    for index in range(int(sting_start * sample_rate), frame_count):
        t = index / sample_rate - sting_start
        envelope = math.exp(-2.0 * t)
        samples[index] += envelope * (
            0.16 * math.sin(2 * math.pi * 31.0 * t)
            + 0.035 * math.sin(2 * math.pi * 173.7 * t)
            + 0.028 * math.sin(2 * math.pi * 233.2 * t)
        )

    peak = max((abs(value) for value in samples), default=1.0)
    gain = min(1.0, 0.72 / max(peak, 0.001))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for value in samples:
            frames.extend(struct.pack("<h", round(max(-1.0, min(1.0, value * gain)) * 32767)))
        handle.writeframes(frames)
    return {
        "file": str(destination),
        "duration_seconds": duration,
        "style": "creeping_dissonant_dread",
        "layers": ["detuned_sub_drone", "brown_room_air", "metal_scrapes", "tightening_sub_pulses", "final_sting"],
        "drone_frequencies": [round(value, 3) for value in frequencies],
        "scrape_events": scrape_events,
        "pulse_events": pulse_events,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", default="output/job.json")
    parser.add_argument("--config", default="config/default.json")
    parser.add_argument("--output", default="output/horror-music.wav")
    args = parser.parse_args()
    job = load_json(args.job)
    config = load_config(args.config)
    voice_report = load_json(Path(config["output_directory"]) / "voice-report.json")
    duration = effective_video_duration(float(voice_report["duration_seconds"]), config, job["job_id"])
    report = generate_music(job["job_id"], duration, Path(args.output))
    Path(args.output).with_name("music-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
