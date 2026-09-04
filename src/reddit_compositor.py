from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any

from .utils import ffprobe, run


def _ass_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def media_details(path: Path) -> tuple[float, bool]:
    probe = ffprobe(path)
    duration = float(probe.get("format", {}).get("duration") or 0)
    has_audio = any(stream.get("codec_type") == "audio" for stream in probe.get("streams", []))
    if duration <= 0:
        raise RuntimeError("Reddit video duration could not be measured")
    return duration, has_audio


def average_luma(source: Path, ffmpeg: str = "ffmpeg") -> float:
    result = run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(source), "-an",
        "-vf", "fps=1,scale=160:-2,signalstats,metadata=print:file=-", "-t", "20",
        "-f", "null", "-",
    ], check=False, timeout=90)
    values = [float(value) for value in re.findall(r"lavfi\.signalstats\.YAVG=([0-9.]+)", result.stdout)]
    return round(sum(values) / len(values), 3) if values else 0.0


def _grade(luma: float) -> str:
    if luma < 32:
        return "eq=brightness=0.10:contrast=1.08:saturation=1.20:gamma=1.35"
    if luma < 52:
        return "eq=brightness=0.04:contrast=1.08:saturation=1.16:gamma=1.12"
    return "eq=brightness=0.00:contrast=1.06:saturation=1.12:gamma=1.00"


def find_hook_start(source: Path, duration: float, hook_duration: float,
                    ffmpeg: str = "ffmpeg") -> float:
    result = run([
        ffmpeg, "-hide_banner", "-loglevel", "info", "-i", str(source), "-an",
        "-vf", r"scale=240:-2,select=gt(scene\,0.16),showinfo", "-frames:v", "18",
        "-f", "null", "-",
    ], check=False, timeout=120)
    changes = [float(value) for value in re.findall(r"pts_time:([0-9.]+)", result.stderr)]
    usable = [value for value in changes if 0.4 <= value <= duration - hook_duration - 0.15]
    if usable:
        return round(usable[len(usable) // 2], 3)
    return round(max(0.0, min(duration - hook_duration, duration * 0.36)), 3)


def _offset(seed: str, index: int, duration: float) -> float:
    digest = hashlib.sha256(f"{seed}:{index}".encode()).digest()
    fraction = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)
    return fraction * max(0.1, duration)


def compose_reddit_short(source: Path, narration: Path, captions: Path, destination: Path,
                         final_duration: float, hook_duration: float, hook_start: float,
                         width: int = 1080, height: int = 1920, fps: int = 30,
                         ffmpeg: str = "ffmpeg",
                         watermark_text: str = "Lululala") -> dict[str, Any]:
    source_duration, has_source_audio = media_details(source)
    luma = average_luma(source, ffmpeg)
    segment_length = 5.2
    remaining = max(0.1, final_duration - hook_duration)
    regular_count = max(1, math.ceil(remaining / segment_length))
    durations = [hook_duration]
    for index in range(regular_count):
        durations.append(min(segment_length, remaining - index * segment_length))
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y",
               "-stream_loop", "-1", "-i", str(source), "-i", str(narration),
               "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.04:sample_rate=48000"]
    split_labels = "".join(f"[raw{index}]" for index in range(len(durations)))
    filters = [f"[0:v]split={len(durations)}{split_labels}"]
    offsets = [hook_start] + [_offset(source.stem, index, source_duration) for index in range(regular_count)]
    for index, (start, length) in enumerate(zip(offsets, durations)):
        zoom = (1.12, 1.05, 1.09, 1.03)[index % 4]
        zoom_w, zoom_h = int(width * zoom) // 2 * 2, int(height * zoom) // 2 * 2
        x = 0 if index % 3 == 0 else (zoom_w - width if index % 3 == 1 else (zoom_w - width) // 2)
        flip = "hflip," if index % 2 == 0 else ""
        filters.append(
            f"[raw{index}]trim=start={start:.3f}:duration={length:.3f},setpts=PTS-STARTPTS,"
            f"{flip}scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
            f"scale={zoom_w}:{zoom_h},crop={width}:{height}:{x}:0,fps={fps},setsar=1,"
            f"{_grade(luma)},"
            f"format=yuv420p[seg{index}]"
        )
    concat_labels = "".join(f"[seg{index}]" for index in range(len(durations)))
    watermark_filter = ""
    cleaned_watermark = " ".join(watermark_text.split())
    if cleaned_watermark:
        watermark_path = destination.parent / "watermark.txt"
        watermark_path.parent.mkdir(parents=True, exist_ok=True)
        watermark_path.write_text(cleaned_watermark, encoding="utf-8")
        watermark_filter = (
            f",drawtext=textfile='{_ass_path(watermark_path)}':font='DejaVu Sans':"
            "fontsize=32:fontcolor=white@0.68:box=1:boxcolor=black@0.22:boxborderw=8:"
            "x=(w-text_w)/2:y=h-text_h-180"
        )
    filters.extend([
        f"{concat_labels}concat=n={len(durations)}:v=1:a=0[sequence]",
        "[sequence]split=2[clean][captionbase]",
        f"[captionbase]crop={width}:400:0:760,boxblur=luma_radius=18:luma_power=2,"
        "eq=brightness=-0.06,format=rgba,colorchannelmixer=aa=0.48[captionblur]",
        f"[clean][captionblur]overlay=0:760,subtitles='{_ass_path(captions)}',"
        f"trim=duration={final_duration:.3f}{watermark_filter},format=yuv420p[vout]",
        f"[1:a]adelay={round(hook_duration * 1000)}:all=1,highpass=f=70,lowpass=f=11000,"
        f"loudnorm=I=-16:TP=-2:LRA=8,apad,atrim=duration={final_duration:.3f}[voice]",
        f"[2:a]lowpass=f=5200,highpass=f=90,volume=0.012,atrim=duration={final_duration:.3f}[bed]",
    ])
    mix = ["[voice]", "[bed]"]
    if has_source_audio:
        filters.append(
            f"[0:a]atrim=start={hook_start:.3f}:duration={hook_duration:.3f},asetpts=PTS-STARTPTS,"
            "volume=0.72,afade=t=out:st=2.25:d=0.5,apad,"
            f"atrim=duration={final_duration:.3f}[hookaudio]"
        )
        mix.append("[hookaudio]")
    filters.append("".join(mix) + f"amix=inputs={len(mix)}:duration=longest:normalize=0,"
                   f"atrim=duration={final_duration:.3f},alimiter=limit=0.88[aout]")
    destination.parent.mkdir(parents=True, exist_ok=True)
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
        "-t", f"{final_duration:.3f}", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-ar", "48000", "-movflags", "+faststart", str(destination),
    ])
    result = run(command, check=False, timeout=1200)
    if result.returncode or not destination.is_file() or destination.stat().st_size < 500_000:
        raise RuntimeError(f"Reddit story composition failed: {result.stderr[-3500:]}")
    return {"hook_start": hook_start, "hook_duration": hook_duration,
            "source_duration": source_duration, "source_has_audio": has_source_audio,
            "source_average_luma": luma,
            "watermark_text": cleaned_watermark,
            "segment_count": len(durations), "segment_durations": durations,
            "source_offsets": offsets}
