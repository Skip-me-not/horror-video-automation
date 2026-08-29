from __future__ import annotations

from pathlib import Path
from typing import Any

from .audio_mixer import mux_continuous_audio
from .config_loader import Settings
from .utils import run


def _render_segment(source: Path, segment: dict[str, Any], destination: Path,
                    settings: Settings, ffmpeg: str) -> None:
    duration = float(segment["end"]) - float(segment["start"])
    kind = segment["type"]
    common = ["-an", "-r", str(settings.fps), "-c:v", "libx264", "-preset", "veryfast",
              "-crf", str(settings.crf), "-pix_fmt", "yuv420p", str(destination)]
    if kind in {"hook", "podcast"}:
        zoom = float(segment.get("crop_variant", 1.0))
        filters = [f"trim=start={float(segment['start']):.3f}:end={float(segment['end']):.3f}", "setpts=PTS-STARTPTS"]
        if kind == "hook":
            filters.extend(["gblur=sigma=7", "eq=brightness=-0.16:saturation=0.7"])
        elif zoom > 1.0:
            scaled_w = round(settings.output_width * zoom / 2) * 2
            scaled_h = round(settings.output_height * zoom / 2) * 2
            filters.extend([f"scale={scaled_w}:{scaled_h}",
                            f"crop={settings.output_width}:{settings.output_height}:(iw-ow)/2:(ih-oh)/2"])
        command = [ffmpeg, "-y", "-i", str(source), "-vf", ",".join(filters), "-t", f"{duration:.3f}", *common]
    else:
        asset = Path(segment["asset"]["local_path"])
        scale_crop = (f"scale={settings.output_width}:{settings.output_height}:force_original_aspect_ratio=increase,"
                      f"crop={settings.output_width}:{settings.output_height}")
        if kind == "reference_image":
            frames = max(1, round(duration * settings.fps))
            vf = (f"{scale_crop},zoompan=z='min(zoom+0.00035,1.035)':d={frames}:"
                  f"s={settings.output_width}x{settings.output_height}:fps={settings.fps},"
                  "eq=brightness=-0.06:saturation=0.78")
            command = [ffmpeg, "-y", "-loop", "1", "-i", str(asset), "-vf", vf,
                       "-t", f"{duration:.3f}", *common]
        else:
            command = [ffmpeg, "-y", "-stream_loop", "-1", "-i", str(asset), "-vf",
                       f"{scale_crop},eq=brightness=-0.06:saturation=0.78", "-t", f"{duration:.3f}", *common]
    result = run(command, check=False)
    if result.returncode or not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"visual segment render failed ({kind}): {result.stderr[-1800:]}")


def compose(source: Path, plan: dict[str, Any], captions: Path, destination: Path,
            temp_directory: Path, settings: Settings, ffmpeg: str = "ffmpeg") -> Path:
    clips = temp_directory / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, segment in enumerate(plan["segments"]):
        path = clips / f"clip-{index:03d}.mp4"
        _render_segment(source, segment, path, settings, ffmpeg)
        paths.append(path)
    concat_file = temp_directory / "visual-concat.txt"
    concat_file.write_text("\n".join(f"file '{str(path.resolve()).replace(chr(92), '/')}'" for path in paths) + "\n",
                           encoding="utf-8")
    visual = temp_directory / "visual-track.mp4"
    result = run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                  "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(settings.crf),
                  "-pix_fmt", "yuv420p", str(visual)], check=False)
    if result.returncode:
        raise RuntimeError(f"visual concat failed: {result.stderr[-2200:]}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return mux_continuous_audio(visual, source, captions, destination,
                                float(plan["final_duration"]), settings.crf, ffmpeg)
