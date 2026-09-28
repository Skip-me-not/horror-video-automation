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
        if card.get("type", "image") == "video":
            command.extend(["-t", f"{scene_duration:.3f}", "-i", card["path"]])
        else:
            command.extend(["-loop", "1", "-framerate", str(fps), "-t", f"{scene_duration:.3f}", "-i", card["path"]])
    command.extend(["-i", str(narration)])
    music = str(config.get("background_music") or "")
    if music:
        if not Path(music).is_file():
            raise FileNotFoundError("licensed music file is missing")
        command.extend(["-i", music])
    filters: list[str] = []
    for index in range(len(cards)):
        if cards[index].get("type", "image") == "video":
            focus_x = max(0.1, min(0.9, float(cards[index].get("focus_x", 0.5))))
            filters.append(
                f"[{index}:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}:x='max(0,min(iw-{width},iw*{focus_x:.3f}-{width / 2:.0f}))',"
                f"setsar=1,tpad=stop_mode=clone:stop_duration=4,"
                f"trim=duration={scene_duration:.3f},setpts=PTS-STARTPTS[v{index}]"
            )
        else:
            movement = "0.0007" if index % 2 == 0 else "0.00045"
            filters.append(
                f"[{index}:v]scale={width}:{height},zoompan=z='min(zoom+{movement},1.045)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={fps},"
                f"setsar=1,tpad=stop_mode=clone:stop_duration=1,"
                f"trim=duration={scene_duration:.3f},setpts=PTS-STARTPTS[v{index}]"
            )
    labels = "".join(f"[v{i}]" for i in range(len(cards)))
    ass_path = str(captions.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    filters.append(
        f"{labels}concat=n={len(cards)}:v=1:a=0,tpad=stop_mode=clone:stop_duration=1,"
        f"trim=duration={final_duration:.3f},setpts=PTS-STARTPTS,subtitles='{ass_path}',format=yuv420p[vout]"
    )
    audio_index = len(cards)
    if music:
        filters.extend([
            f"[{audio_index}:a]highpass=f=70,lowpass=f=12000,loudnorm=I=-16:TP=-2:LRA=7,"
            f"apad,atrim=duration={final_duration:.3f},asplit=2[voice][side]",
            f"[{audio_index + 1}:a]volume=-28dB,atrim=duration={final_duration:.3f},"
            f"afade=t=out:st={max(0, final_duration - 1):.3f}:d=1[music]",
            "[music][side]sidechaincompress=threshold=0.02:ratio=2:attack=20:release=300[ducked]",
            "[voice][ducked]amix=inputs=2:duration=first:normalize=0[aout]",
        ])
    else:
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
