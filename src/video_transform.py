from __future__ import annotations

from pathlib import Path

from .config_loader import Settings
from .utils import run


def _crop_filter(settings: Settings) -> str:
    if settings.crop_mode == "vertical_canvas":
        return (
            f"split=2[background][foreground];"
            f"[background]scale={settings.output_width}:{settings.output_height}:force_original_aspect_ratio=increase,"
            f"crop={settings.output_width}:{settings.output_height},gblur=sigma=30[blurred];"
            f"[foreground]scale={settings.output_width}:-2:force_original_aspect_ratio=decrease[front];"
            f"[blurred][front]overlay=(W-w)/2:(H-h)/2"
        )
    x = {"left": "0", "right": "iw-ow", "center": "(iw-ow)/2", "auto_simple": "(iw-ow)/2"}[settings.crop_mode]
    return (f"scale={settings.output_width}:{settings.output_height}:force_original_aspect_ratio=increase,"
            f"crop={settings.output_width}:{settings.output_height}:x='{x}':y='(ih-oh)/2'")


def transform_source(source: Path, destination: Path, start: float, end: float,
                     settings: Settings, ffmpeg: str = "ffmpeg") -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    video_filters = []
    if settings.horizontal_flip:
        video_filters.append("hflip")
    video_filters.extend([_crop_filter(settings), f"setpts=PTS/{settings.source_speed}",
                          f"fps={settings.fps}", "format=yuv420p"])
    command = [ffmpeg, "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source),
               "-filter_complex", f"[0:v]{','.join(video_filters)}[v];[0:a]atempo={settings.source_speed}[a]",
               "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", str(settings.crf), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
               "-movflags", "+faststart", str(destination)]
    result = run(command, check=False)
    if result.returncode or not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"source transformation failed: {result.stderr[-2000:]}")
    return destination
