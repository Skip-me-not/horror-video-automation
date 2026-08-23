from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    bank_path: Path = ROOT / "data" / "script_bank.json"
    used_path: Path = ROOT / "data" / "used_scripts.json"
    state_path: Path = ROOT / "data" / "generation_state.json"
    performance_path: Path = ROOT / "data" / "performance.json"
    output_dir: Path = ROOT / "output"
    quality_threshold: int = 40
    max_generation_retries: int = 30
    title_similarity_threshold: float = 0.82
    hook_similarity_threshold: float = 0.84
    story_similarity_threshold: float = 0.76
    tts_voice: str = "en-US-AndrewMultilingualNeural"
    tts_rate: str = "+12%"
    visual_provider: str = "auto"
    upload_privacy: str = "public"

    @classmethod
    def from_env(cls, root: Path | None = None) -> "Settings":
        base = (root or ROOT).resolve()
        return cls(
            root=base,
            bank_path=Path(os.getenv("SCRIPT_BANK_PATH", base / "data/script_bank.json")),
            used_path=Path(os.getenv("USED_SCRIPTS_PATH", base / "data/used_scripts.json")),
            state_path=Path(os.getenv("GENERATION_STATE_PATH", base / "data/generation_state.json")),
            performance_path=Path(os.getenv("PERFORMANCE_PATH", base / "data/performance.json")),
            output_dir=Path(os.getenv("OUTPUT_DIR", base / "output")),
            quality_threshold=_int("SCRIPT_QUALITY_THRESHOLD", 40),
            max_generation_retries=_int("MAX_GENERATION_RETRIES", 30),
            title_similarity_threshold=_float("TITLE_SIMILARITY_THRESHOLD", 0.82),
            hook_similarity_threshold=_float("HOOK_SIMILARITY_THRESHOLD", 0.84),
            story_similarity_threshold=_float("STORY_SIMILARITY_THRESHOLD", 0.76),
            tts_voice=os.getenv("EDGE_TTS_VOICE", "en-US-AndrewMultilingualNeural"),
            tts_rate=os.getenv("EDGE_TTS_RATE", "+12%"),
            visual_provider=os.getenv("VISUAL_PROVIDER", "auto"),
            upload_privacy=os.getenv("YOUTUBE_PRIVACY_STATUS", "public"),
        )

    def validate(self) -> None:
        if not 0 <= self.quality_threshold <= 50:
            raise ValueError("SCRIPT_QUALITY_THRESHOLD must be between 0 and 50")
        if self.max_generation_retries < 1:
            raise ValueError("MAX_GENERATION_RETRIES must be positive")
        if self.upload_privacy not in {"public", "private", "unlisted"}:
            raise ValueError("YOUTUBE_PRIVACY_STATUS is invalid")
