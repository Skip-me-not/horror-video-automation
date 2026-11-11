#!/usr/bin/env python3
"""End-to-end deterministic BL Shorts pipeline used locally and by GitHub Actions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from scripts.ai_optimizer import optimize_packaging
from scripts.bl_engine import BLEngineError, ROOT, generate_package, load_state, read_json, write_json_atomic
from scripts.bl_ranked_renderer import ranked_package, render_ranked
from scripts.bl_renderer import render
from scripts.bl_source import NoEligibleKpopContentError, collect_kpop_ranked
from scripts.daily_quota import myanmar_date, scheduled_slot_target, summary, write_summary

OUTPUT = ROOT / "output"
REDDIT_STATE = ROOT / "data" / "reddit_state.json"


def github_output(name: str, value: str) -> None:
    destination = os.environ.get("GITHUB_OUTPUT", "").strip()
    if destination:
        with Path(destination).open("a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def daily_ids() -> list[str]:
    if not REDDIT_STATE.exists():
        return []
    payload = read_json(REDDIT_STATE)
    return list(payload.get("daily_uploads", {}).get(myanmar_date(), []))


def should_skip_for_daily_quota(*, event_name: str, dry_run: bool,
                                current_count: int, slot_target: int | None) -> bool:
    """Apply quota guards to scheduled retries, never to manual dispatches."""
    return (
        not dry_run
        and event_name == "schedule"
        and slot_target is not None
        and current_count >= slot_target
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Structured story JSON; omit to use queue/configured feeds")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-review", action="store_true", help="Render manual-review content but never publish it")
    parser.add_argument("--narration-mode", choices=("auto", "required", "text-only"), default="auto")
    parser.add_argument(
        "--ai-mode",
        choices=("auto", "off", "required"),
        default=os.environ.get("AI_MODE", "auto"),
        help="Use one low-token AI packaging call, disable it, or fail if unavailable",
    )
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    current_ids = daily_ids()
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    slot_target = scheduled_slot_target() if event_name == "schedule" else None
    # Scheduled publishing deliberately targets one upload per day. A manual
    # workflow_dispatch remains an operator-requested run and is not quota-limited.
    if should_skip_for_daily_quota(
        event_name=event_name,
        dry_run=args.dry_run,
        current_count=len(current_ids),
        slot_target=slot_target,
    ):
        github_output("publish", "false")
        print(f"DAILY SLOT TARGET ALREADY MET: {slot_target} upload(s)")
        return
    if args.input:
        input_path = (ROOT / args.input).resolve() if not args.input.is_absolute() else args.input.resolve()
        if ROOT.resolve() not in input_path.parents:
            raise BLEngineError("Story input must stay inside the repository")
        story, origin = read_json(input_path), str(input_path.relative_to(ROOT))
        package = generate_package(story, load_state())
        decision = package["verification"]["decision"]
        if decision != "auto_publish" and not args.allow_review:
            raise BLEngineError(f"Story cannot auto-publish: {package['verification']}")
        write_json_atomic(OUTPUT / "story.json", story)
        write_json_atomic(OUTPUT / "package.json", package)
        report = render(OUTPUT / "package.json", narration_mode=args.narration_mode, allow_review=args.allow_review)
    else:
        stories, origin = collect_kpop_ranked(6)
        optimization = optimize_packaging(
            stories,
            token=os.environ.get("GITHUB_MODELS_TOKEN", "").strip(),
            endpoint=os.environ.get("AI_ENDPOINT", "https://models.github.ai/inference/chat/completions"),
            model=os.environ.get("AI_MODEL", "openai/gpt-4o-mini"),
            mode=args.ai_mode,
        )
        package = ranked_package(stories, load_state(), optimization)
        decision = package["verification"]["decision"]
        write_json_atomic(OUTPUT / "story.json", {"format": "retention_ranked_countdown_v2", "stories": stories})
        write_json_atomic(OUTPUT / "package.json", package)
        write_json_atomic(OUTPUT / "ai_optimization.json", optimization.as_dict())
        report = render_ranked(package)
    publish = report["passed"] and decision == "auto_publish" and not args.dry_run
    github_output("publish", "true" if publish else "false")
    github_output("story_id", package["story_id"])
    print(f"PIPELINE READY: origin={origin} decision={decision} dry_run={args.dry_run} publish={publish}")


if __name__ == "__main__":
    try:
        main()
    except NoEligibleKpopContentError as exc:
        github_output("publish", "false")
        if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
            print(f"SCHEDULE SKIPPED: {exc}")
            raise SystemExit(0)
        raise SystemExit(f"ERROR: {exc}") from exc
    except BLEngineError as exc:
        github_output("publish", "false")
        raise SystemExit(f"ERROR: {exc}") from exc
