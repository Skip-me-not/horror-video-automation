from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.common import (
        ValidationError, effective_video_duration, load_config, load_json, resolve_asset, sanitize_output_name,
    )
except ModuleNotFoundError:  # Support direct script execution.
    from common import (
        ValidationError, effective_video_duration, load_config, load_json, resolve_asset, sanitize_output_name,
    )

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN = os.getenv("FFPROBE_BIN", "ffprobe")


def ffprobe(path: str | Path) -> dict[str, Any]:
    result = subprocess.run(
        [FFPROBE_BIN, "-v", "error", "-show_streams", "-show_format",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def parse_probe(data: dict[str, Any]) -> dict[str, Any]:
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    try:
        duration = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        duration = 0
    return {"has_video": video is not None, "has_audio": audio is not None,
            "duration": duration, "video": video, "audio": audio}


def validate_render(path: Path, expected_duration: float) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValidationError("rendered output is empty")
    parsed = parse_probe(ffprobe(path))
    if not parsed["has_video"] or not parsed["has_audio"]:
        raise ValidationError("rendered output must contain audio and video")
    if parsed["duration"] < 1 or abs(parsed["duration"] - expected_duration) > 1.0:
        raise ValidationError("rendered duration does not match narration")
    return parsed


def ffmpeg_filter_path(path: Path) -> str:
    value = path.resolve().as_posix()
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def render(
    job: dict,
    config: dict,
    project: Path,
    narration: Path,
    captions: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    background = resolve_asset(project / "assets/backgrounds", job["background_file"])
    if not background.is_file():
        raise FileNotFoundError(f"background is missing: {background}")
    if not narration.is_file():
        raise FileNotFoundError(f"narration is missing: {narration}")
    ambience = None
    if job.get("ambience_file"):
        ambience = resolve_asset(project / "assets/ambience", job["ambience_file"])
        if not ambience.is_file():
            raise FileNotFoundError(f"ambience is missing: {ambience}")

    narration_info = parse_probe(ffprobe(narration))
    narration_duration = narration_info["duration"]
    duration = effective_video_duration(narration_duration, config, job["job_id"])
    source_info = parse_probe(ffprobe(background))
    source_video = source_info["video"] or {}
    source_w = int(source_video.get("width", 0))
    source_h = int(source_video.get("height", 0))
    target_w, target_h = int(config["output_width"]), int(config["output_height"])
    if source_w <= 0 or source_h <= 0:
        raise ValidationError("background video dimensions could not be detected")
    fade = min(float(config.get("fade_seconds", 1.5)), duration / 4)
    fade_out = max(0, duration - fade)
    captions_path = captions or (project / config["output_directory"] / "captions.ass")
    if not captions_path.is_file():
        raise FileNotFoundError(f"captions are missing: {captions_path}")
    output_dir = project / config["output_directory"]
    output_dir.mkdir(parents=True, exist_ok=True)
    watermark_text_file = output_dir / "watermark.txt"
    watermark_text_file.write_text(
        str(job.get("watermark_text") or config["watermark_text"]), encoding="utf-8"
    )
    watermark_text_filter = (
        f"drawtext=textfile='{ffmpeg_filter_path(watermark_text_file)}':"
        "font='DejaVu Sans':fontsize=40:"
        "fontcolor=white@0.88:box=1:boxcolor=black@0.32:boxborderw=11:"
        "x=(w-text_w)/2:"
        f"y={int(config['watermark_margin_y'])},"
    )
    base_video = (
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},fps={int(config['fps'])},"
        "eq=brightness=-0.02:contrast=1.04:saturation=0.78,"
        "noise=alls=2:allf=t,"
        f"{watermark_text_filter}"
        f"subtitles='{ffmpeg_filter_path(captions_path)}',format=yuv420p,"
        f"fade=t=in:st=0:d={fade},fade=t=out:st={fade_out}:d={fade}"
    )
    command = [FFMPEG_BIN, "-hide_banner", "-loglevel", "warning", "-y"]
    if background.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        command += ["-loop", "1", "-framerate", str(int(config["fps"])), "-i", str(background)]
    else:
        command += ["-stream_loop", "-1", "-i", str(background)]
    filters: list[str] = [base_video + "[v]"]
    narration_index = 1
    command += ["-i", str(narration)]
    intro_delay = int(config["narration_intro_delay_ms"])
    filters.append(f"[{narration_index}:a]asplit=2[narrmain][narrghost]")
    voice_filter = (
        f"[narrmain]adelay={intro_delay}:all=1,"
        f"apad=pad_dur={duration},atrim=duration={duration},"
        f"afade=t=in:st={intro_delay / 1000}:d={fade},"
        f"afade=t=out:st={fade_out}:d={fade}[voice]"
    )
    filters.append(voice_filter)
    filters.append(
        "[narrghost]areverse,asetrate=48000*0.82,aresample=48000,atempo=1.219512,"
        "highpass=f=120,lowpass=f=1800,aecho=0.8:0.55:170|340:0.16|0.07,"
        f"volume={float(config['whisper_volume'])},adelay=1250:all=1,"
        f"apad=pad_dur={duration},atrim=duration={duration}[whisper]"
    )
    if ambience:
        command += ["-stream_loop", "-1", "-i", str(ambience)]
        ambience_index = narration_index + 1
        filters += [
            f"[{ambience_index}:a]volume={float(config['ambience_volume'])},"
            f"atrim=duration={duration},afade=t=in:st=0:d={fade},"
            f"afade=t=out:st={fade_out}:d={fade}[amb]",
        ]
    else:
        command += [
            "-f", "lavfi", "-i",
            "anoisesrc=color=brown:amplitude=0.35:sample_rate=48000",
        ]
        ambience_index = narration_index + 1
        filters += [
            f"[{ambience_index}:a]highpass=f=35,lowpass=f=240,"
            f"volume={float(config['ambience_volume'])},atrim=duration={duration},"
            f"afade=t=in:st=0:d={fade},afade=t=out:st={fade_out}:d={fade}[amb]",
        ]
    mix_labels = ["[voice]", "[amb]", "[whisper]"]
    next_audio_index = ambience_index + 1
    sfx = project / config["output_directory"] / "horror-sfx.wav"
    if sfx.is_file():
        command += ["-i", str(sfx)]
        filters.append(
            f"[{next_audio_index}:a]volume={float(config['sfx_volume'])},"
            f"atrim=duration={duration},afade=t=in:st=0:d=0.4,"
            f"afade=t=out:st={fade_out}:d={fade}[sfx]"
        )
        mix_labels.append("[sfx]")
        next_audio_index += 1
    music = project / config["output_directory"] / "horror-music.wav"
    if music.is_file():
        command += ["-i", str(music)]
        filters.append(
            f"[{next_audio_index}:a]highpass=f=32,lowpass=f=7200,"
            "aecho=0.8:0.45:360|720:0.14|0.06,"
            "loudnorm=I=-20:TP=-3:LRA=8,"
            f"volume={float(config['music_volume'])},atrim=duration={duration},"
            f"afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out}:d={fade}[music]"
        )
        mix_labels.append("[music]")
    filters.append(
        "".join(mix_labels)
        + f"amix=inputs={len(mix_labels)}:duration=longest:normalize=0,"
        + f"atrim=duration={duration},alimiter=limit=0.8414[a]"
    )
    output = output_dir / sanitize_output_name(job["job_id"])
    command += [
        "-filter_complex", ";".join(filters),
        "-map", "[v]", "-map", "[a]", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", str(config["encoding_preset"]),
        "-crf", str(config["crf"]), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-metadata", f"title={job['title']}", str(output),
    ]
    subprocess.run(command, check=True)
    report = validate_render(output, duration)
    report["source_background"] = {"width": source_w, "height": source_h}
    report["narration_duration"] = narration_duration
    report["output_file"] = str(output)
    (output_dir / "render-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--config", default="config/default.json")
    parser.add_argument("--narration", default="output/narration.wav")
    parser.add_argument("--captions", default="output/captions.ass")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    output, report = render(
        load_json(args.job), load_config(args.config), project,
        Path(args.narration), Path(args.captions),
    )
    print(json.dumps({"output": str(output), "duration": report["duration"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
