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


@dataclass(frozen=True)
class InteractiveSettings:
    root: Path = ROOT
    history_path: Path = ROOT / "data" / "history.json"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    min_duration: float = 15.0
    max_duration: float = 30.0
    history_limit: int = 100
    privacy: str = "private"

    @classmethod
    def from_env(cls, root: Path | None = None) -> "InteractiveSettings":
        base = (root or ROOT).resolve()
        settings = cls(
            root=base,
            history_path=Path(os.getenv("INTERACTIVE_HISTORY_PATH", base / "data/history.json")),
            width=_int("VIDEO_WIDTH", 1080),
            height=_int("VIDEO_HEIGHT", 1920),
            fps=_int("VIDEO_FPS", 30),
            min_duration=_float("MIN_DURATION", 15.0),
            max_duration=_float("MAX_DURATION", 30.0),
            history_limit=_int("HISTORY_LIMIT", 100),
            privacy=os.getenv("YOUTUBE_PRIVACY_STATUS", "private"),
        )
        if settings.privacy not in {"private", "unlisted", "public"}:
            raise ValueError("YOUTUBE_PRIVACY_STATUS must be private, unlisted, or public")
        return settings
