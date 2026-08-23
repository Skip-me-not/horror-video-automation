from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path


class ExistingMediaPipelineRenderer:
    """Runs the repository's tested TTS/visual/audio/FFmpeg stages."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _run(self, *arguments: str) -> None:
        subprocess.run([sys.executable, *arguments], cwd=self.root, check=True)

    def render(self, job_path: Path) -> Path:
        provider = os.getenv("TTS_PROVIDER", "edge").casefold()
        narration = self.root / "output" / "narration.wav"
        if provider == "edge":
            import json
            from .config import Settings
            from .subtitles import SubtitleWriter
            from .tts import EdgeTTSNarrator, audio_duration
            job = json.loads(job_path.read_text(encoding="utf-8"))
            settings = Settings.from_env(self.root)
            narration = self.root / "output" / "narration.mp3"
            timing = self.root / "output" / "word-timings.json"
            timings = EdgeTTSNarrator(settings.tts_voice, settings.tts_rate).synthesize(job["story"], narration, timing)
            SubtitleWriter().from_json(
                timing, self.root / "output" / "captions.ass",
                emphasis_terms=[str(value) for value in job.get("important_terms", [])],
            )
            duration = audio_duration(narration)
            (self.root / "output" / "voice-report.json").write_text(json.dumps({
                "provider": "edge", "seed": None, "chunks": 1,
                "chunk_durations_seconds": [round(duration, 3)], "pauses_ms": [],
                "duration_seconds": round(duration, 3), "runtime_seconds": None,
                "narration_file": str(narration),
                "captions_file": str(self.root / "output" / "captions.ass"),
                "word_boundaries": len(timings),
            }, indent=2), encoding="utf-8")
        else:
            self._run("scripts/generate_voice.py", "--job", str(job_path), "--provider", provider)
        self._run("scripts/fetch_background.py", "--job", str(job_path))
        self._run("scripts/prepare_visual_track.py", "--job", str(job_path), "--narration", str(narration))
        self._run("scripts/generate_sfx.py", "--job", str(job_path), "--output", "output/horror-sfx.wav")
        self._run("scripts/generate_music.py", "--job", str(job_path), "--output", "output/horror-music.wav")
        self._run("scripts/render_video.py", "--job", str(job_path), "--narration", str(narration), "--captions", "output/captions.ass")
        import json
        report = json.loads((self.root / "output/render-report.json").read_text(encoding="utf-8"))
        return Path(report["output_file"])
