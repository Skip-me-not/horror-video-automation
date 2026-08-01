from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.common import ValidationError
from scripts.render_video import parse_probe, render


def test_ffprobe_result_parsing():
    parsed = parse_probe({
        "streams": [{"codec_type": "video", "width": 1280}, {"codec_type": "audio"}],
        "format": {"duration": "12.5"},
    })
    assert parsed["has_video"] and parsed["has_audio"]
    assert parsed["duration"] == 12.5


def test_missing_media_fails(valid_job, config, tmp_path):
    with pytest.raises(FileNotFoundError, match="background"):
        render(valid_job, config, tmp_path, tmp_path / "missing.wav")


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg is required")
def test_lightweight_fixture_render(valid_job, config, tmp_path):
    backgrounds = tmp_path / "assets/backgrounds"
    backgrounds.mkdir(parents=True)
    (tmp_path / "output").mkdir()
    valid_job["background_file"] = "background.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x111111:s=320x180:r=30:d=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(backgrounds / "background.mp4")
    ], check=True)
    narration = tmp_path / "narration.wav"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=1.2",
        str(narration)
    ], check=True)
    captions = tmp_path / "captions.ass"
    captions.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Caption,Arial,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,50,50,300,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Caption,,0,0,0,,Do not look behind you.\n",
        encoding="utf-8",
    )
    config["video_duration_seconds"] = 2
    output, report = render(valid_job, config, tmp_path, narration, captions)
    assert output.is_file()
    assert report["has_video"] and report["has_audio"]
    assert 1.9 < report["duration"] < 2.1
