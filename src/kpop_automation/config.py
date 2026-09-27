from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import CATEGORIES


class ConfigError(ValueError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    channel, content, schedule, video = (
        payload.get("channel", {}), payload.get("content", {}),
        payload.get("schedule", {}), payload.get("video", {}),
    )
    weights = content.get("category_weights", {})
    if set(weights) != set(CATEGORIES):
        raise ConfigError("category_weights must contain all eight supported categories")
    if abs(sum(float(x) for x in weights.values()) - 1.0) > 0.001:
        raise ConfigError("category_weights must total 1.0")
    if schedule.get("timezone") != "Asia/Yangon" or len(schedule.get("slots", [])) != 4:
        raise ConfigError("schedule must define four Asia/Yangon slots")
    if not 30 <= int(content.get("minimum_seconds", 0)) <= int(content.get("maximum_seconds", 0)) <= 60:
        raise ConfigError("content runtime must remain between 30 and 60 seconds")
    if (int(video.get("width", 0)), int(video.get("height", 0)), int(video.get("fps", 0))) != (1080, 1920, 30):
        raise ConfigError("production video must be 1080x1920 at 30 FPS")
    channel["auto_publish"] = os.getenv("AUTO_PUBLISH", str(channel.get("auto_publish", False))).lower() == "true"
    channel["trusted_sources_only"] = os.getenv(
        "TRUSTED_SOURCES_ONLY", str(channel.get("trusted_sources_only", True))
    ).lower() == "true"
    channel["upload_privacy"] = os.getenv("UPLOAD_PRIVACY", str(channel.get("upload_privacy", "private")))
    if channel["upload_privacy"] not in {"private", "unlisted", "public"}:
        raise ConfigError("upload_privacy must be private, unlisted, or public")
    payload["channel"] = channel
    return payload
