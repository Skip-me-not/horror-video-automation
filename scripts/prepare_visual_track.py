from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

try:
    from scripts.common import ValidationError, effective_video_duration, load_config, load_json, resolve_asset
    from scripts.render_video import ffprobe, parse_probe
except ModuleNotFoundError:
    from common import ValidationError, effective_video_duration, load_config, load_json, resolve_asset
    from render_video import ffprobe, parse_probe

STILL_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def build_scene_filter(index: int, width: int, height: int, fps: int, segment: float) -> str:
    """Normalize geometry and sample aspect ratio before concatenating providers."""
    return (
        f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1/1,fps={fps},trim=duration={segment:.3f},"
        f"setpts=PTS-STARTPTS[v{index}]"
    )


def prepare(job: dict, config: dict, project: Path, narration: Path) -> tuple[Path, dict]:
    backgrounds = job.get("background_files") or [job.get("background_file")]
    if not isinstance(backgrounds, list) or not backgrounds or any(not isinstance(item, str) for item in backgrounds):
        raise ValidationError("background_files must be a non-empty filename list")
    paths = [resolve_asset(project / "assets" / "backgrounds", name) for name in backgrounds]
    if any(not path.is_file() for path in paths):
        raise FileNotFoundError("one or more selected background scenes are missing")
    narration_seconds = parse_probe(ffprobe(narration))["duration"]
    duration = effective_video_duration(narration_seconds, config, job["job_id"])
    segment = duration / len(paths)
    width, height, fps = int(config["output_width"]), int(config["output_height"]), int(config["fps"])
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y"]
    filters: list[str] = []
    for index, path in enumerate(paths):
        if path.suffix.lower() in STILL_EXTENSIONS:
            command += ["-loop", "1", "-framerate", str(fps), "-i", str(path)]
        else:
            command += ["-stream_loop", "-1", "-i", str(path)]
        filters.append(build_scene_filter(index, width, height, fps, segment))
    labels = "".join(f"[v{index}]" for index in range(len(paths)))
    filters.append(f"{labels}concat=n={len(paths)}:v=1:a=0[v]")
    destination = project / "assets" / "backgrounds" / f"visual-track-{job['job_id']}.mp4"
    command += [
        "-filter_complex", ";".join(filters), "-map", "[v]", "-t", f"{duration:.3f}",
        "-an", "-c:v", "libx264", "-preset", str(config["encoding_preset"]),
        "-crf", str(config["crf"]), "-pix_fmt", "yuv420p", str(destination),
    ]
    subprocess.run(command, check=True)
    job["background_file"] = destination.name
    report = {
        "visual_track": str(destination), "duration_seconds": duration,
        "scene_count": len(paths), "scene_seconds": round(segment, 3),
        "source_files": [path.name for path in paths],
    }
    Path(config["output_directory"]).mkdir(parents=True, exist_ok=True)
    (Path(config["output_directory"]) / "visual-track-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return destination, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--config", default="config/default.json")
    parser.add_argument("--narration", default="output/narration.wav")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    job_path = Path(args.job)
    job = load_json(job_path)
    output, report = prepare(job, load_config(args.config), project, Path(args.narration))
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    print(json.dumps({**report, "visual_track": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
