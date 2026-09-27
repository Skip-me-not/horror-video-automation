from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from src.subtitles import SubtitleWriter
from src.utils import run


def render(cards: list[dict[str, Any]], narration: Path, timings: list[dict[str, Any]],
           script: dict[str, Any], output_dir: Path, duration: float, config: dict[str, Any]) -> dict[str, Any]:
    ffmpeg = os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("FFmpeg is required")
    width, height, fps = int(config["width"]), int(config["height"]), int(config["fps"])
    final_duration = duration + 0.55
    captions = SubtitleWriter().from_timings(
        timings, output_dir / "captions.ass", [script["hook"], *script.get("tags", [])],
        hook_text=str(script["hook"]), hook_duration=min(2.8, final_duration / 5),
    )
    scene_duration = final_duration / len(cards)
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y"]
    for card in cards:
        command.extend(["-loop", "1", "-framerate", str(fps), "-t", f"{scene_duration:.3f}", "-i", card["path"]])
    command.extend(["-i", str(narration)])
    filters: list[str] = []
    for index in range(len(cards)):
        movement = "0.0007" if index % 2 == 0 else "0.00045"
        filters.append(
            f"[{index}:v]scale={width}:{height},zoompan=z='min(zoom+{movement},1.045)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={fps},"
            f"setsar=1[v{index}]"
        )
    labels = "".join(f"[v{i}]" for i in range(len(cards)))
    ass_path = str(captions.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    filters.append(
        f"{labels}concat=n={len(cards)}:v=1:a=0,tpad=stop_mode=clone:stop_duration=1,"
        f"trim=duration={final_duration:.3f},setpts=PTS-STARTPTS,subtitles='{ass_path}',format=yuv420p[vout]"
    )
    audio_index = len(cards)
    filters.append(
        f"[{audio_index}:a]highpass=f=70,lowpass=f=12000,loudnorm=I=-16:TP=-2:LRA=7,"
        f"apad,atrim=duration={final_duration:.3f}[aout]"
    )
    destination = output_dir / "short.mp4"
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
        "-t", f"{final_duration:.3f}", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "21", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(destination),
    ])
    result = run(command, check=False, timeout=1200)
    if result.returncode or not destination.is_file() or destination.stat().st_size < 500_000:
        raise RuntimeError(f"FFmpeg render failed: {result.stderr[-3000:]}")
    (output_dir / "cover.png").write_bytes(Path(cards[0]["path"]).read_bytes())
    (output_dir / "transcript.txt").write_text(str(script["narration"]), encoding="utf-8")
    report = {"path": str(destination), "duration": final_duration, "scene_count": len(cards),
              "width": width, "height": height, "fps": fps, "captions": str(captions)}
    (output_dir / "production.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
