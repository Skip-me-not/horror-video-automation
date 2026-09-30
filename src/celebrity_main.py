from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.kpop_automation.cli import _slot_default  # noqa: E402
from src.kpop_automation.pipeline import produce  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce one rights-checked Korean celebrity news Short")
    parser.add_argument("--dry-run", action="store_true", help="Never reserve a slot or upload")
    parser.add_argument("--story-limit", type=int, default=1)
    parser.add_argument("--slot", default=_slot_default())
    parser.add_argument("--category", default="")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "kpop.yaml")
    args = parser.parse_args()
    if args.story_limit != 1:
        parser.error("one invocation produces at most one verified Short; use scheduled slots for additional stories")
    result = produce(ROOT, args.config, args.slot, args.category, args.dry_run, args.fixture)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
