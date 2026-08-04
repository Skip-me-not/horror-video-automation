from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ALLOWED_MEDIA = {
    "background_file": {
        ".mp4",
        ".mov",
        ".mkv",
        ".webm",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    },
    "ambience_file": {
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".ogg",
    },
    "thumbnail_file": {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    },
}

SAFE_FILENAME = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$"
)

SAFE_JOB_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
)


class ValidationError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(
        encoding="utf-8"
    ) as handle:
        value = json.load(handle)

    if not isinstance(value, dict):
        raise ValidationError(
            f"{path} must contain a JSON object"
        )

    return value


def load_config(
    path: str | Path,
) -> dict[str, Any]:

    config = load_json(path)

    required = {
        "tts_provider",
        "tts_seed",
        "tts_chunk_characters",
        "paragraph_pause_ms",
        "section_pause_ms",
        "narration_max_seconds",
        "narration_max_speedup",
        "narration_intro_delay_ms",
        "creepy_voice_filter",
        "caption_max_characters",
        "caption_font_size",
        "caption_margin_vertical",
        "video_duration_seconds",
        "min_story_characters",
        "max_story_characters",
        "max_payload_bytes",
        "output_width",
        "output_height",
        "fps",
        "crf",
        "encoding_preset",
        "watermark_text",
        "watermark_margin_y",
        "ambience_volume",
        "music_volume",
        "sfx_volume",
        "whisper_volume",
        "pexels_default_query",
        "pexels_max_download_bytes",
        "output_directory",
        "default_privacy_status",
    }

    missing = required - config.keys()

    if missing:
        raise ValidationError(
            f"configuration missing: "
            f"{', '.join(sorted(missing))}"
        )

    #
    # TTS
    #
    if config["tts_provider"] not in {
        "chatterbox",
        "kokoro",
    }:
        raise ValidationError(
            "tts_provider must be chatterbox or kokoro"
        )

    if not 100 <= int(
        config["tts_chunk_characters"]
    ) <= 1000:
        raise ValidationError(
            "tts_chunk_characters must be between 100 and 1000"
        )

    if not 0 <= int(
        config["paragraph_pause_ms"]
    ) <= 3000:
        raise ValidationError(
            "paragraph_pause_ms must be between 0 and 3000"
        )

    if not 0 <= int(
        config["section_pause_ms"]
    ) <= 5000:
        raise ValidationError(
            "section_pause_ms must be between 0 and 5000"
        )

    #
    # Story limits
    #
    min_story = int(
        config["min_story_characters"]
    )

    max_story = int(
        config["max_story_characters"]
    )

    if not (
        0 < min_story < max_story
    ):
        raise ValidationError(
            "story length limits are invalid"
        )

    #
    # Video dimensions
    #
    resolution = (
        int(config["output_width"]),
        int(config["output_height"]),
    )

    if resolution not in {
        (1080, 1920),
        (720, 1280),
    }:
        raise ValidationError(
            "Shorts resolution must be "
            "1080x1920 or 720x1280"
        )

    #
    # FPS
    #
    if int(config["fps"]) not in {
        24,
        25,
        30,
    }:
        raise ValidationError(
            "fps must be 24, 25, or 30"
        )

    #
    # Encoding
    #
    if not 16 <= int(
        config["crf"]
    ) <= 32:
        raise ValidationError(
            "crf must be between 16 and 32"
        )

    if config["encoding_preset"] not in {
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
    }:
        raise ValidationError(
            "encoding_preset is not CPU-runner safe"
        )

    #
    # Audio volumes
    #
    if not 0 <= float(
        config["ambience_volume"]
    ) <= 0.25:
        raise ValidationError(
            "ambience_volume must be between 0 and 0.25"
        )

    if not 0 <= float(
        config["sfx_volume"]
    ) <= 0.5:
        raise ValidationError(
            "sfx_volume must be between 0 and 0.5"
        )

    if not 0 <= float(
        config["music_volume"]
    ) <= 1.0:
        raise ValidationError(
            "music_volume must be between 0 and 1.0"
        )

    if not 0 <= float(
        config["whisper_volume"]
    ) <= 0.08:
        raise ValidationError(
            "whisper_volume must be between 0 and 0.08"
        )

    #
    # Watermark
    #
    if not 0 <= int(
        config["watermark_margin_y"]
    ) <= 400:
        raise ValidationError(
            "watermark_margin_y is invalid"
        )

    watermark_text = config[
        "watermark_text"
    ]

    if (
        not isinstance(
            watermark_text,
            str,
        )
        or not 1 <= len(
            watermark_text
        ) <= 32
    ):
        raise ValidationError(
            "watermark_text must contain 1 to 32 characters"
        )

    #
    # Pexels
    #
    pexels_query = config[
        "pexels_default_query"
    ]

    if (
        not isinstance(
            pexels_query,
            str,
        )
        or not 3 <= len(
            pexels_query
        ) <= 80
    ):
        raise ValidationError(
            "pexels_default_query must contain 3 to 80 characters"
        )

    if not 5_000_000 <= int(
        config["pexels_max_download_bytes"]
    ) <= 250_000_000:
        raise ValidationError(
            "pexels_max_download_bytes is invalid"
        )

    #
    # Video timing
    #
    duration = float(
        config["video_duration_seconds"]
    )

    narration_limit = float(
        config["narration_max_seconds"]
    )

    if (
        not 15 <= duration <= 60
        or not 5 <= narration_limit < duration
    ):
        raise ValidationError(
            "video and narration duration limits are invalid"
        )

    if not 1 <= float(
        config["narration_max_speedup"]
    ) <= 1.2:
        raise ValidationError(
            "narration_max_speedup must be between 1.0 and 1.2"
        )

    if not 0 <= int(
        config["narration_intro_delay_ms"]
    ) <= 3000:
        raise ValidationError(
            "narration_intro_delay_ms must be between 0 and 3000"
        )

    #
    # Captions
    #
    if not 30 <= int(
        config["caption_max_characters"]
    ) <= 120:
        raise ValidationError(
            "caption_max_characters must be between 30 and 120"
        )

    #
    # YouTube privacy
    #
    if config["default_privacy_status"] not in {
        "private",
        "unlisted",
        "public",
    }:
        raise ValidationError(
            "default_privacy_status must be "
            "private, unlisted, or public"
        )

    #
    # Output directory
    #
    output_directory = Path(
        str(
            config["output_directory"]
        )
    )

    if (
        output_directory.is_absolute()
        or ".." in output_directory.parts
    ):
        raise ValidationError(
            "output_directory must stay within the project"
        )

    return config


def safe_filename(
    value: str,
    field: str,
    *,
    allow_empty: bool = False,
) -> str:

    if allow_empty and value == "":
        return value

    if (
        not isinstance(value, str)
        or not SAFE_FILENAME.fullmatch(value)
    ):
        raise ValidationError(
            f"{field} contains an invalid filename"
        )

    if (
        value in {".", ".."}
        or "/" in value
        or "\\" in value
        or Path(value).name != value
    ):
        raise ValidationError(
            f"{field} must be a basename without path components"
        )

    suffix = Path(
        value
    ).suffix.lower()

    if suffix not in ALLOWED_MEDIA[field]:
        raise ValidationError(
            f"{field} has unsupported format "
            f"{suffix or '(none)'}"
        )

    return value


def resolve_asset(
    root: str | Path,
    filename: str,
) -> Path:

    root_path = Path(
        root
    ).resolve()

    candidate = (
        root_path / filename
    ).resolve()

    if candidate.parent != root_path:
        raise ValidationError(
            "asset path escaped its configured directory"
        )

    return candidate


def sanitize_output_name(
    value: str,
) -> str:

    clean = re.sub(
        r"[^A-Za-z0-9_-]+",
        "-",
        value.strip(),
    )

    clean = clean.strip(
        "-_"
    ).lower()

    return (
        clean[:64]
        or "video"
    ) + ".mp4"
