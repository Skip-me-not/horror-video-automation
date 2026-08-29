from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    root: Path
    output_width: int = 1080
    output_height: int = 1920
    fps: int = 30
    min_final_duration: float = 65.0
    target_final_duration: float = 110.0
    max_final_duration: float = 175.0
    hard_max_duration: float = 180.0
    source_speed: float = 1.10
    horizontal_flip: bool = True
    original_video_zoom: float = 1.08
    require_original_video: bool = True
    hook_min_seconds: float = 2.0
    hook_max_seconds: float = 5.0
    broll_min_seconds: float = 2.5
    broll_max_seconds: float = 4.5
    target_broll_ratio: float = 0.25
    min_broll_count: int = 3
    target_broll_count: int = 5
    max_broll_count: int = 7
    max_static_speaker_seconds: float = 9.0
    download_max_height: int = 720
    analysis_preview_height: int = 360
    crop_mode: str = "center"
    enable_pexels: bool = True
    enable_pixabay: bool = True
    crf: int = 22
    encoder: str = "libx264"
    encoder_preset: str = "veryfast"
    authorization_required: bool = True
    min_source_duration: float = 600.0
    max_source_duration: float = 10800.0
    artifact_retention_days: int = 5
    max_sources_per_run: int = 2
    stop_after_first_success: bool = True
    debug_artifacts: bool = False
    disk_warning_free_gb: float = 5.0
    disk_abort_free_gb: float = 3.0
    range_download_padding_seconds: float = 3.0


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_settings(root: Path) -> Settings:
    raw = read_json(root / "config" / "settings.json")
    valid = {field.name for field in fields(Settings)} - {"root"}
    values: dict[str, Any] = {key: value for key, value in raw.items() if key in valid}
    settings = Settings(root=root, **values)
    if not 1.0 <= settings.source_speed <= 2.0:
        raise ValueError("source_speed must be between 1.0 and 2.0")
    if not 1.0 <= settings.original_video_zoom <= 1.25:
        raise ValueError("original_video_zoom must be between 1.0 and 1.25")
    if not 60 <= settings.min_final_duration <= settings.max_final_duration <= settings.hard_max_duration <= 180:
        raise ValueError("duration settings must remain within 60-180 seconds")
    if settings.crop_mode not in {"center", "left", "right", "auto_simple", "vertical_canvas"}:
        raise ValueError("unsupported crop_mode")
    if not 1 <= settings.target_broll_count <= settings.max_broll_count <= 7:
        raise ValueError("B-roll counts must satisfy 1 <= target <= max <= 7")
    return settings
