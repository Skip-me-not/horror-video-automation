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


CHORDS = (
    (0.0, 7.5, (73.42, 110.00, 146.83, 174.61)),
    (7.5, 15.0, (58.27, 87.31, 116.54, 146.83)),
    (15.0, 22.5, (49.00, 73.42, 98.00, 116.54)),
    (22.5, 30.0, (55.00, 82.41, 110.00, 130.81, 155.56)),
)
MELODY = (293.66, 349.23, 440.00, 392.00, 349.23, 311.13, 293.66, 261.63)


def smooth_envelope(position: float, length: float, attack: float, release: float) -> float:
    return max(0.0, min(1.0, position / max(attack, 0.001),
                        (length - position) / max(release, 0.001)))


def generate_music(job_id: str, duration: float, destination: Path,
                   sample_rate: int = 48000) -> dict[str, object]:
    rng = random.Random(f"music:{job_id}")
    samples = [0.0] * int(duration * sample_rate)

    # Sustained detuned pad following an audible minor-key chord progression.
    chord_index = 0
    for start in [index * 7.5 for index in range(math.ceil(duration / 7.5))]:
        notes = CHORDS[chord_index % len(CHORDS)][2]
        chord_index += 1
        segment_end = min(start + 7.5, duration)
        segment_length = segment_end - start
        detunes = [rng.uniform(-0.22, 0.22) for _ in notes]
        for index in range(int(start * sample_rate), int(segment_end * sample_rate)):
            t = index / sample_rate - start
            envelope = smooth_envelope(t, segment_length, 1.4, 1.6)
            value = 0.0
            for note, detune in zip(notes, detunes):
                frequency = note * (2 ** (detune / 12))
                value += math.sin(2 * math.pi * frequency * t)
                value += 0.28 * math.sin(2 * math.pi * frequency * 2 * t)
            samples[index] += value * envelope * (0.082 / len(notes))

    # A sparse decaying melody makes this music, rather than another sound effect.
    melody_events: list[dict[str, object]] = []
    starts = [2.0 + index * 3.5 for index in range(max(1, math.ceil((duration - 2.0) / 3.5)))]
    for event_index, start in enumerate(starts):
        if start >= duration:
            continue
        frequency = MELODY[event_index % len(MELODY)]
        end = min(duration, start + 2.8)
        for index in range(int(start * sample_rate), int(end * sample_rate)):
            t = index / sample_rate - start
            envelope = math.exp(-1.55 * t)
            value = (
                math.sin(2 * math.pi * frequency * t)
                + 0.42 * math.sin(2 * math.pi * frequency * 2.01 * t)
                + 0.16 * math.sin(2 * math.pi * frequency * 3.98 * t)
            )
            samples[index] += 0.055 * envelope * value
        melody_events.append({"time": start, "frequency": frequency})

    # Slow bass pulses provide a cinematic rhythm without overpowering narration.
    for start in [index * 3.75 for index in range(math.ceil(duration / 3.75))]:
        if start >= duration:
            continue
        end = min(duration, start + 1.8)
        for index in range(int(start * sample_rate), int(end * sample_rate)):
            t = index / sample_rate - start
            samples[index] += 0.10 * math.exp(-2.2 * t) * math.sin(2 * math.pi * 36.71 * t)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for value in samples:
            frames.extend(struct.pack("<h", round(max(-1.0, min(1.0, value)) * 32767)))
        handle.writeframes(frames)
    return {
        "file": str(destination),
        "duration_seconds": duration,
        "style": "cinematic_minor_horror",
        "progression": ["D minor", "B-flat", "G minor", "A diminished"],
        "melody_events": melody_events,
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
