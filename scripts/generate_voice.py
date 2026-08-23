from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

try:
    from scripts.common import ValidationError, load_config, load_json
except ModuleNotFoundError:  # Support direct script execution.
    from common import ValidationError, load_config, load_json

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN = os.getenv("FFPROBE_BIN", "ffprobe")

SENTENCE = re.compile(r"(?<=[.!?])(?:[\"”']*)\s+")


def split_text(text: str, max_characters: int) -> list[str]:
    """Split on paragraph/sentence boundaries without discarding text."""
    chunks: list[str] = []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    for paragraph in paragraphs:
        sentences = [s.strip() for s in SENTENCE.split(paragraph) if s.strip()]
        current = ""
        for sentence in sentences:
            if len(sentence) > max_characters:
                if current:
                    chunks.append(current)
                    current = ""
                words = sentence.split()
                part = ""
                for word in words:
                    candidate = f"{part} {word}".strip()
                    if part and len(candidate) > max_characters:
                        chunks.append(part)
                        part = word
                    else:
                        part = candidate
                if part:
                    chunks.append(part)
                continue
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > max_characters:
                chunks.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            chunks.append(current)
    if not chunks:
        raise ValidationError("story produced no narration chunks")
    return chunks


def pauses_for_chunks(
    text: str,
    chunks: list[str],
    paragraph_pause_ms: int,
    section_pause_ms: int,
) -> list[int]:
    """Assign longer pauses where the original text has paragraph/section breaks."""
    pauses = [250] * len(chunks)
    cursor = 0
    for index, chunk in enumerate(chunks[:-1]):
        found = text.find(chunk, cursor)
        cursor = found + len(chunk) if found >= 0 else cursor
        next_found = text.find(chunks[index + 1], cursor)
        between = text[cursor:next_found] if next_found >= 0 else ""
        newline_count = between.count("\n")
        if newline_count >= 3:
            pauses[index] = section_pause_ms
        elif newline_count >= 2:
            pauses[index] = paragraph_pause_ms
    if pauses:
        pauses[-1] = 0
    return pauses


def split_captions(text: str, max_characters: int) -> list[str]:
    """Create short sentence-aware caption cards without losing words."""
    captions: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        current = ""
        for sentence in [part.strip() for part in SENTENCE.split(paragraph) if part.strip()]:
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > max_characters:
                captions.append(current)
                current = sentence
            else:
                current = candidate
            while len(current) > max_characters:
                words = current.split()
                split_at = max(
                    1,
                    next(
                        (index for index in range(len(words), 0, -1)
                         if len(" ".join(words[:index])) <= max_characters),
                        1,
                    ),
                )
                captions.append(" ".join(words[:split_at]))
                current = " ".join(words[split_at:])
        if current:
            captions.append(current)
    if not captions:
        raise ValidationError("story produced no captions")
    return captions


def ass_timestamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, hundredths = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{hundredths:02d}"


def ass_escape(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def write_captions(
    story: str,
    narration_seconds: float,
    config: dict,
    output: Path,
) -> None:
    captions = split_captions(story, int(config["caption_max_characters"]))
    intro = int(config["narration_intro_delay_ms"]) / 1000
    weights = [max(1, len(re.sub(r"\s+", "", caption))) for caption in captions]
    total_weight = sum(weights)
    cursor = intro
    events: list[str] = []
    for caption, weight in zip(captions, weights):
        span = narration_seconds * weight / total_weight
        end = cursor + span
        display_caption = "\n".join(
            textwrap.wrap(
                caption.upper(),
                width=max(20, int(config["output_width"]) // 41),
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
        events.append(
            f"Dialogue: 0,{ass_timestamp(cursor)},{ass_timestamp(end)},Caption,,0,0,0,,"
            f"{{\\fad(35,70)\\fscx108\\fscy108\\t(0,120,\\fscx100\\fscy100)}}"
            f"{ass_escape(display_caption)}"
        )
        cursor = end
    output.write_text(
        "\n".join([
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {int(config['output_width'])}",
            f"PlayResY: {int(config['output_height'])}",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Caption,DejaVu Sans,{int(config['caption_font_size'])},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,7,2,5,80,80,{int(config['caption_margin_vertical'])},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
            "",
        ]),
        encoding="utf-8",
        newline="\n",
    )


class TTSProvider(Protocol):
    sample_rate: int

    def synthesize(self, text: str, output: Path) -> None: ...


@dataclass
class ChatterboxNanoProvider:
    config: dict

    def __post_init__(self) -> None:
        import torch
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        torch.set_num_threads(max(1, int(os.getenv("TTS_CPU_THREADS", os.cpu_count() or 2))))
        self.torch = torch
        self.model = ChatterboxTurboTTS.from_pretrained(device="cpu", nano=True)
        reference = str(self.config.get("voice_reference_path", "")).strip()
        if reference:
            ref_path = Path(reference)
            if not ref_path.is_file():
                raise ValidationError("configured permitted reference voice does not exist")
            self.model.prepare_conditionals(str(ref_path), exaggeration=0.0)
        self.sample_rate = int(self.model.sr)

    def synthesize(self, text: str, output: Path) -> None:
        import soundfile as sf

        wav = self.model.generate(
            text,
            temperature=float(self.config["chatterbox_temperature"]),
            top_p=float(self.config["chatterbox_top_p"]),
            top_k=int(self.config["chatterbox_top_k"]),
            repetition_penalty=float(self.config["chatterbox_repetition_penalty"]),
        )
        sf.write(output, wav.squeeze(0).cpu().numpy(), self.sample_rate, subtype="PCM_16")


@dataclass
class KokoroProvider:
    config: dict

    def __post_init__(self) -> None:
        from kokoro import KPipeline

        self.pipeline = KPipeline(lang_code="a")
        self.sample_rate = 24000

    def synthesize(self, text: str, output: Path) -> None:
        import numpy as np
        import soundfile as sf

        segments = [
            audio.cpu().numpy() if hasattr(audio, "cpu") else np.asarray(audio)
            for _, _, audio in self.pipeline(
                text,
                voice=self.config["kokoro_voice"],
                speed=float(self.config["kokoro_speed"]),
            )
        ]
        if not segments:
            raise RuntimeError("Kokoro returned no audio")
        sf.write(output, np.concatenate(segments), self.sample_rate, subtype="PCM_16")


def create_provider(name: str, config: dict) -> TTSProvider:
    if name == "chatterbox":
        return ChatterboxNanoProvider(config)
    if name == "kokoro":
        return KokoroProvider(config)
    raise ValidationError(f"unsupported TTS provider: {name}")


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def normalize_and_join(
    chunks: list[Path], output: Path, pauses_ms: list[int], config: dict
) -> None:
    if len(chunks) != len(pauses_ms):
        raise ValueError("every narration chunk must have a pause value")
    prepared: list[Path] = []
    for index, chunk in enumerate(chunks):
        padded = chunk.with_name(f"{chunk.stem}-padded.wav")
        pad = pauses_ms[index] / 1000
        subprocess.run(
            [FFMPEG_BIN, "-hide_banner", "-loglevel", "error", "-y", "-i", str(chunk),
             "-af", f"apad=pad_dur={pad}", "-ar", "48000", "-ac", "1", str(padded)],
            check=True,
        )
        prepared.append(padded)
    concat_file = output.parent / "narration-concat.txt"
    concat_file.write_text(
        "".join(f"file '{path.resolve().as_posix()}'\n" for path in prepared),
        encoding="utf-8",
    )
    joined = output.with_name("narration-joined.wav")
    voice_filter = str(config["creepy_voice_filter"]).strip()
    filters = [value for value in [voice_filter, "loudnorm=I=-16:TP=-1.5:LRA=11", "alimiter=limit=0.8414"] if value]
    subprocess.run(
        [FFMPEG_BIN, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
         "-safe", "0", "-i", str(concat_file), "-af",
         ",".join(filters), "-ar", "48000", "-ac", "1", str(joined)],
        check=True,
    )
    duration = probe_duration(joined)
    limit = float(config["narration_max_seconds"])
    speed = duration / limit if duration > limit else 1.0
    if speed > float(config["narration_max_speedup"]):
        raise ValidationError(
            f"narration is {duration:.1f}s and exceeds the configured Shorts limit; "
            "shorten the story"
        )
    subprocess.run(
        [FFMPEG_BIN, "-hide_banner", "-loglevel", "error", "-y", "-i", str(joined),
         "-af", f"atempo={speed:.6f}", "-ar", "48000", "-ac", "1", str(output)],
        check=True,
    )


def generate(job: dict, config: dict, provider_name: str, output_dir: Path) -> dict:
    started = time.monotonic()
    random.seed(int(config["tts_seed"]))
    try:
        import numpy as np
        np.random.seed(int(config["tts_seed"]))
        import torch
        torch.manual_seed(int(config["tts_seed"]))
    except ImportError:
        pass
    chunks_text = split_text(job["story"], int(config["tts_chunk_characters"]))
    pauses_ms = pauses_for_chunks(
        job["story"],
        chunks_text,
        int(config["paragraph_pause_ms"]),
        int(config.get("section_pause_ms", config["paragraph_pause_ms"])),
    )
    provider = create_provider(provider_name, config)
    chunk_dir = output_dir / "voice-chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    durations: list[float] = []
    for index, text in enumerate(chunks_text):
        path = chunk_dir / f"chunk-{index:04d}.wav"
        provider.synthesize(text, path)
        if not path.is_file() or path.stat().st_size < 1024:
            raise RuntimeError(f"TTS chunk {index} is empty")
        duration = probe_duration(path)
        if duration < max(0.3, len(text) / 100):
            raise RuntimeError(f"TTS chunk {index} is abnormally short ({duration:.2f}s)")
        paths.append(path)
        durations.append(duration)
    narration = output_dir / "narration.wav"
    normalize_and_join(paths, narration, pauses_ms, config)
    narration_duration = probe_duration(narration)
    captions = output_dir / "captions.ass"
    write_captions(job["story"], narration_duration, config, captions)
    report = {
        "provider": provider_name,
        "seed": int(config["tts_seed"]),
        "chunks": len(paths),
        "chunk_durations_seconds": [round(d, 3) for d in durations],
        "pauses_ms": pauses_ms,
        "duration_seconds": round(narration_duration, 3),
        "runtime_seconds": round(time.monotonic() - started, 3),
        "narration_file": str(narration),
        "captions_file": str(captions),
    }
    (output_dir / "voice-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--config", default="config/default.json")
    parser.add_argument("--provider", choices=["chatterbox", "kokoro"])
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    config = load_config(args.config)
    job = load_json(args.job)
    provider = args.provider or os.getenv("TTS_PROVIDER") or config["tts_provider"]
    output_dir = Path(args.output_dir or config["output_directory"])
    output_dir.mkdir(parents=True, exist_ok=True)
    report = generate(job, config, provider, output_dir)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
