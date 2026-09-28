from __future__ import annotations

import json
from pathlib import Path

from src.kpop_automation.music import ensure_original_theme
from src.kpop_automation.video import render


def edit(root: Path, job: dict, scenes: list[dict], timings: list[dict], seconds: float,
         output: Path, hook: str) -> Path:
    preset = json.loads((root / "presets" / f"{job['style']}.json").read_text(encoding="utf-8"))
    music = root / "assets" / "music" / "lululala-theme.wav"
    ensure_original_theme(music)
    config = {**preset, "background_music": str(music)}
    result = render(scenes, output / "voice.mp3", timings,
                    {"hook": hook, "narration": job["script"], "tags": [job["person"]]},
                    output, seconds, config)
    final = output / "final.mp4"
    Path(result["path"]).replace(final)
    return final
