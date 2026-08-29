from __future__ import annotations

from pathlib import Path

from .utils import run


def mux_continuous_audio(video: Path, source_with_audio: Path, captions: Path, destination: Path,
                         duration: float, crf: int, ffmpeg: str = "ffmpeg") -> Path:
    caption_path = str(captions.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    command = [ffmpeg, "-y", "-i", str(video), "-i", str(source_with_audio),
               "-vf", f"tpad=stop_mode=clone:stop_duration=2,trim=duration={duration:.3f},"
                      f"setpts=PTS-STARTPTS,ass='{caption_path}'",
               "-map", "0:v:0", "-map", "1:a:0",
               "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
               "-movflags", "+faststart", str(destination)]
    result = run(command, check=False)
    if result.returncode or not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"audio/caption mux failed: {result.stderr[-2500:]}")
    return destination
