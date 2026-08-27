from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import InteractiveSettings
from src.game_generator import GAME_TYPES, GameGenerator, validate_game
from src.history import HistoryStore, sha256_file
from src.metadata import generate_metadata
from src.renderer import InteractiveRenderer
from src.scene_generator import InteractiveSceneGenerator
from src.upload_youtube import YouTubeAuthenticationError, upload_video
from src.validator import validate_video


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _ffprobe_binary(root: Path) -> str | None:
    configured = os.getenv("FFPROBE_BIN")
    if configured:
        return configured
    discovered = shutil.which("ffprobe")
    if discovered:
        return discovered
    local = root / ".test-tools" / "ffprobe.exe"
    return str(local) if local.is_file() else None


def run(game_type: str | None, seed: int | None, no_upload: bool) -> dict[str, Any]:
    settings = InteractiveSettings.from_env()
    output = settings.root / "output"
    output.mkdir(parents=True, exist_ok=True)
    history = HistoryStore(settings.history_path, settings.history_limit)
    generator = GameGenerator(settings.root / "data/hooks.json", history.recent_signatures())
    rng = random.Random(seed)
    game: dict[str, Any] | None = None
    generation_errors: list[str] = []
    for attempt in range(3):
        try:
            game = generator.generate(rng, game_type)
            validate_game(game)
            break
        except (ValueError, KeyError, TypeError) as exc:
            generation_errors.append(f"attempt {attempt + 1}: {exc}")
    if game is None:
        chosen = game_type or "choose_door"
        game = generator.fallback(chosen)
        validate_game(game)
    _write_json(output / "game.json", game)
    phases = InteractiveSceneGenerator().generate_game(game)
    _write_json(output / "timeline.json", phases)
    video = output / "short.mp4"
    renderer = InteractiveRenderer(settings.root, settings.width, settings.height, settings.fps)
    render_error: Exception | None = None
    render_report: dict[str, Any] | None = None
    for _ in range(2):
        try:
            render_report = renderer.render(game, phases, video)
            render_error = None
            break
        except (OSError, RuntimeError) as exc:
            render_error = exc
    if render_error or render_report is None:
        raise RuntimeError(f"render failed after retry: {render_error}")
    validation = validate_video(video, settings.width, settings.height,
                                59.5, 60.5,
                                ffprobe=_ffprobe_binary(settings.root))
    _write_json(output / "validation.json", {
        "valid": validation.valid, "errors": validation.errors, "probe": validation.probe,
    })
    if not validation.valid:
        raise RuntimeError("video validation failed: " + "; ".join(validation.errors))
    metadata = generate_metadata(game, settings.privacy)
    _write_json(output / "metadata.json", metadata)
    video_hash = sha256_file(video)
    upload_log = output / "upload.log"
    duplicate = history.contains_hash(video_hash)
    youtube_video_id: str | None = None
    if duplicate:
        upload_log.write_text("Duplicate SHA-256 found in history; upload skipped.\n", encoding="utf-8")
    elif no_upload:
        upload_log.write_text("No-upload mode: generation and validation succeeded.\n", encoding="utf-8")
    else:
        try:
            youtube_video_id = upload_video(video, metadata, upload_log)
        except YouTubeAuthenticationError as exc:
            upload_log.write_text(f"AUTHENTICATION ERROR: {exc}\n", encoding="utf-8")
            raise
    record = {
        "game_type": game["game_type"], "setting": game["setting"], "hook": game["hook"],
        "monster": game["monster"], "choices": game.get("choices", []),
        "correct_answer": game.get("correct_choice", game.get("target")), "ending": game["reveal"],
        "title": metadata["title"], "video_hash": video_hash,
        "youtube_video_id": youtube_video_id, "uploaded": bool(youtube_video_id),
        "seed": seed, "duplicate_skipped": duplicate,
    }
    history.append(record)
    report = {"game": game, "metadata": metadata, "render": render_report,
              "video_hash": video_hash, "youtube_video_id": youtube_video_id,
              "uploaded": bool(youtube_video_id), "duplicate_skipped": duplicate,
              "generation_errors": generation_errors}
    _write_json(output / "run-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an interactive horror YouTube Short")
    parser.add_argument("--game", choices=GAME_TYPES)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--no-upload", action="store_true", help="render and validate without YouTube upload")
    arguments = parser.parse_args()
    try:
        report = run(arguments.game, arguments.seed, arguments.no_upload)
    except YouTubeAuthenticationError as exc:
        print(f"AUTHENTICATION ERROR: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"PIPELINE ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"uploaded": report["uploaded"], "youtube_video_id": report["youtube_video_id"],
                      "game_type": report["game"]["game_type"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
