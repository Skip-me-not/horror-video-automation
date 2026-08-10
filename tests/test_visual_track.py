from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.prepare_visual_track import build_scene_filter, prepare


def test_scene_filter_normalizes_sample_aspect_ratio():
    value = build_scene_filter(2, 1080, 1920, 30, 6.94)
    assert "crop=1080:1920,setsar=1/1,fps=30" in value
    assert value.endswith("setpts=PTS-STARTPTS[v2]")


def ffmpeg_available() -> bool:
    ffmpeg = os.getenv("FFMPEG_BIN", "ffmpeg")
    ffprobe = os.getenv("FFPROBE_BIN", "ffprobe")
    return bool(shutil.which(ffmpeg)) and (Path(ffprobe).is_file() or bool(shutil.which(ffprobe)))


@pytest.mark.skipif(not ffmpeg_available(), reason="FFmpeg and ffprobe are required")
def test_mixed_sar_scenes_can_be_concatenated(config, tmp_path):
    ffmpeg = os.getenv("FFMPEG_BIN", "ffmpeg")
    backgrounds = tmp_path / "assets" / "backgrounds"
    backgrounds.mkdir(parents=True)
    for index, sar in enumerate(("1/1", "4/3"), start=1):
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=0x111111:s=320x180:r=10:d=1",
            "-vf", f"setsar={sar}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(backgrounds / f"scene-{index}.mp4"),
        ], check=True)
    narration = tmp_path / "narration.wav"
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=1",
        str(narration),
    ], check=True)
    config.update(
        output_width=320, output_height=568, fps=10,
        minimum_video_duration_seconds=2, maximum_video_duration_seconds=2,
        output_directory=str(tmp_path / "output"),
    )
    job = {
        "job_id": "mixed-sar", "background_file": "scene-1.mp4",
        "background_files": ["scene-1.mp4", "scene-2.mp4"],
    }
    output, report = prepare(job, config, tmp_path, narration)
    assert output.is_file()
    assert report["scene_count"] == 2
    assert 1.9 <= report["duration_seconds"] <= 2.1
