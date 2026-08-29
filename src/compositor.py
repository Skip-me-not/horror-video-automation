from __future__ import annotations

from pathlib import Path
from typing import Any

from .config_loader import Settings
from .utils import run


def _ass_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _fill_frame(width: int, height: int) -> str:
    return (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1")


def compose(source: Path, plan: dict[str, Any], captions: Path, destination: Path,
            temp_directory: Path, settings: Settings, ffmpeg: str = "ffmpeg",
            source_trim_start: float = 0.0, source_duration: float | None = None) -> Path:
    """Compose source, B-roll, captions, and continuous audio in one full-resolution encode."""
    del temp_directory  # retained in the API for callers; no intermediate media is created
    final_duration = float(plan["final_duration"])
    source_length = source_duration or final_duration * settings.source_speed
    command = [ffmpeg, "-y", "-i", str(source)]
    broll = [item for item in plan["segments"]
             if item["type"] in {"broll_video", "reference_image"} and item.get("asset")]
    for segment in broll:
        asset = str(segment["asset"]["local_path"])
        if segment["type"] == "reference_image":
            command.extend(["-loop", "1", "-framerate", str(settings.fps), "-i", asset])
        else:
            command.extend(["-stream_loop", "-1", "-i", asset])

    hook_end = float((plan["segments"] or [{}])[0].get("end", 0.0))
    filters = [
        (f"[0:v]trim=start={source_trim_start:.3f}:end={source_trim_start + source_length:.3f},"
         f"setpts=(PTS-STARTPTS)/{settings.source_speed},hflip,{_fill_frame(settings.output_width, settings.output_height)},"
         f"fps={settings.fps},format=yuv420p,gblur=sigma=5:enable='between(t,0,{hook_end:.3f})'[base0]"),
        (f"[0:a]atrim=start={source_trim_start:.3f}:end={source_trim_start + source_length:.3f},"
         f"asetpts=PTS-STARTPTS,atempo={settings.source_speed}[aout]"),
    ]
    current = "base0"
    for index, segment in enumerate(broll, start=1):
        duration = float(segment["end"]) - float(segment["start"])
        start = float(segment["start"])
        asset_filter = _fill_frame(settings.output_width, settings.output_height)
        if segment["type"] == "reference_image":
            asset_filter += (f",zoompan=z='min(zoom+0.0003,1.035)':d=1:"
                             f"s={settings.output_width}x{settings.output_height}:fps={settings.fps}")
        filters.append(
            f"[{index}:v]trim=duration={duration:.3f},setpts=PTS-STARTPTS+{start:.3f}/TB,"
            f"{asset_filter},eq=brightness=-0.06:saturation=0.78[asset{index}]"
        )
        output_label = f"mix{index}"
        filters.append(
            f"[{current}][asset{index}]overlay=0:0:eof_action=pass:shortest=0:"
            f"enable='between(t,{start:.3f},{float(segment['end']):.3f})'[{output_label}]"
        )
        current = output_label
    filters.append(f"[{current}]trim=duration={final_duration:.3f},setpts=PTS-STARTPTS,"
                   f"ass='{_ass_path(captions)}'[vout]")

    destination.parent.mkdir(parents=True, exist_ok=True)
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
        "-t", f"{final_duration:.3f}", "-c:v", settings.encoder,
        "-preset", settings.encoder_preset, "-crf", str(settings.crf),
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart", str(destination),
    ])
    result = run(command, check=False, timeout=1200)
    if result.returncode or not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"single-pass composition failed: {result.stderr[-3000:]}")
    return destination
