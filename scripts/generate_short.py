from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline import HorrorShortPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate, validate, and optionally upload one horror Short.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Select and plan only; never render or upload.")
    mode.add_argument("--no-upload", action="store_true", help="Render and validate without publishing.")
    parser.add_argument("--script-id", help="Use a specific READY incident, such as EV0001.")
    parser.add_argument("--reserve-only", action="store_true", help="Persist a selection without rendering.")
    args = parser.parse_args()
    try:
        pipeline = HorrorShortPipeline()
        if args.reserve_only:
            job = pipeline.reserve(args.script_id)
            result = {"status": "reserved", "script_id": job["script_id"], "job_id": job["job_id"]}
        else:
            result = pipeline.run(dry_run=args.dry_run, no_upload=args.no_upload, script_id=args.script_id)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"Short generation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
