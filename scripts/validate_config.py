#!/usr/bin/env python3
"""Validate the deterministic Reddit Shorts configuration."""

from __future__ import annotations

import argparse
import os
import shutil

from scripts.reddit_source import load_idols, parse_subreddits
from scripts.content_quality import load_quality_config
from scripts.render_idol_short import DEFAULT_CHANNEL_NAME, OUTPUT_DIR, STATE_PATH, load_state
from scripts.render_short import (
    QUOTES_PATH,
    ShortsError,
    load_quotes,
    load_state as load_legacy_state,
    validate_channel_name,
)
from scripts.bl_engine import load_catalogs, load_state as load_bl_state


def require_environment(names: list[str]) -> list[str]:
    return [name for name in names if not os.environ.get(name, "").strip()]


def check_tools() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise ShortsError("ffmpeg and ffprobe must both be installed")


def check_output_directory() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    probe = OUTPUT_DIR / ".write-test"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()


def validate_reddit_short(require_youtube: bool) -> None:
    required = []
    if require_youtube:
        required.extend(["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"])
    missing = require_environment(required)
    if missing:
        raise ShortsError("Missing required configuration: " + ", ".join(missing))
    validate_channel_name(os.environ.get("CHANNEL_NAME", "").strip() or DEFAULT_CHANNEL_NAME)
    parse_subreddits(os.environ.get("INPUT_SUBREDDITS", "kpop,kpopthoughts,kpop_uncensored"))
    idols = load_idols()
    load_quality_config()
    load_state(STATE_PATH)
    check_tools()
    check_output_directory()
    print(
        f"Configuration is valid; {len(idols)} idols are available. "
        "Reddit and music are credential-free; upload privacy is public."
    )


def validate_legacy(require_youtube: bool) -> None:
    required = ["PEXELS_API_KEY", "OPENVERSE_CLIENT_ID", "OPENVERSE_CLIENT_SECRET", "CHANNEL_NAME"]
    if require_youtube:
        required.extend(["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"])
    missing = require_environment(required)
    if missing:
        raise ShortsError("Missing required configuration: " + ", ".join(missing))
    validate_channel_name(os.environ["CHANNEL_NAME"])
    check_tools()
    load_quotes(QUOTES_PATH)
    load_legacy_state()
    check_output_directory()
    print("Legacy configuration is valid.")


def validate_bl_short(require_youtube: bool) -> None:
    required = []
    if require_youtube:
        required.extend(["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"])
    missing = require_environment(required)
    if missing:
        raise ShortsError("Missing required configuration: " + ", ".join(missing))
    validate_channel_name(os.environ.get("CHANNEL_NAME", "").strip() or "Lululala")
    config, manifest, metadata = load_catalogs()
    load_bl_state()
    check_tools()
    check_output_directory()
    if not config.get("feeds") and not os.environ.get("BL_SOURCE_FEEDS_JSON", "").strip():
        print("WARNING: no production BL feeds configured; scheduled runs require queue stories or BL_SOURCE_FEEDS_JSON")
    print(f"BL configuration is valid: {len(manifest['templates'])} templates, "
          f"{len(config['layouts'])} layouts, {len(metadata['title_patterns'])} title patterns.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("bl-short", "reddit-short", "reddit-ai", "reddit-idol", "legacy"), default="legacy")
    parser.add_argument("--require-youtube", action="store_true")
    args = parser.parse_args()
    if args.mode == "bl-short":
        validate_bl_short(args.require_youtube)
    elif args.mode in {"reddit-short", "reddit-ai", "reddit-idol"}:
        validate_reddit_short(args.require_youtube)
    else:
        validate_legacy(args.require_youtube)


if __name__ == "__main__":
    try:
        main()
    except (ShortsError, RuntimeError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
