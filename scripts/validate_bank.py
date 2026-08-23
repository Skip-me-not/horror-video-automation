from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import Settings
from src.duplicate_detector import DuplicateDetector
from src.script_bank import EVIDENCE_TYPES, ScriptBank
from src.script_judge import ScriptJudge


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate format, quality, and uniqueness of the script bank.")
    parser.add_argument("--bank", type=Path)
    args = parser.parse_args()
    settings = Settings.from_env()
    path = args.bank or settings.bank_path
    try:
        bank = ScriptBank(path, settings.used_path)
        errors = bank.validate()
        detector = DuplicateDetector(
            settings.title_similarity_threshold,
            settings.hook_similarity_threshold,
            settings.story_similarity_threshold,
        )
        judge = ScriptJudge()
        accepted: list[dict[str, object]] = []
        for item in bank.items:
            if not 60 <= int(item.get("word_count", 0)) <= 100:
                errors.append(f"{item.get('id')}: word count must be 60-100")
            score = judge.score(item)
            if score.total < settings.quality_threshold:
                errors.append(f"{item.get('id')}: quality {score.total}/50")
            duplicate = detector.check(item, accepted)
            if duplicate.duplicate:
                errors.append(f"{item.get('id')}: duplicate ({duplicate.reason} {duplicate.score:.2f})")
            accepted.append(item)
        if len(bank.items) == 500:
            found_evidence = {str(item.get("evidence_type")) for item in bank.items}
            if not found_evidence <= EVIDENCE_TYPES or len(found_evidence) < 2:
                errors.append("500-item bank must contain at least two valid evidence types")
        if errors:
            for error in errors[:50]:
                print(f"ERROR: {error}")
            print(f"Bank invalid: {len(errors)} error(s).", file=sys.stderr)
            return 2
        counts = Counter(str(item["category"]) for item in bank.items)
        sources = {str(item["source_url"]) for item in bank.items}
        evidence = {str(item["evidence_type"]) for item in bank.items}
        print(f"Fact bank valid: {len(bank.items)} scripts, {len(sources)} sources, {len(counts)} categories, {len(evidence)} evidence types, {sum(1 for i in bank.items if i['status'] == 'ready')} READY.")
        return 0
    except (ValueError, OSError) as exc:
        print(f"Bank validation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
