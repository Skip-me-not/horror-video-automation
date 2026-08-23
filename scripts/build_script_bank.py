from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import Settings
from src.duplicate_detector import DuplicateDetector
from src.fact_generator import FactScriptGenerator
from src.fact_source_provider import LibraryOfCongressProvider, WikimediaProvider, load_source_cache, save_source_cache
from src.script_bank import ScriptBank, utc_now
from src.script_judge import ScriptJudge


def build(target: int, settings: Settings, source_cache: Path, refresh_sources: bool = False) -> int:
    if not 1 <= target <= 500:
        raise ValueError("target must be between 1 and 500")
    bank = ScriptBank(settings.bank_path, settings.used_path)
    errors = bank.validate()
    if errors:
        raise ValueError("existing bank is invalid: " + "; ".join(errors[:5]))
    if bank.items and any(item.get("content_type") != "sourced_horror_fact" for item in bank.items):
        raise ValueError("existing bank contains fictional stories; move or clear it before building the fact bank")
    if len(bank.items) >= target:
        print(f"Bank already contains {len(bank.items)}/{target} scripts.")
        return 0
    previous_sources = load_source_cache(source_cache)
    sources = [] if refresh_sources else previous_sources
    if len(sources) < target:
        print(f"Fetching {target} source records from the Library of Congress...")
        fetched = []
        if refresh_sources and not sources:
            fetched.extend(LibraryOfCongressProvider(delay_seconds=0.6).fetch(min(1000, target + 500)))
        completed_wiki_categories = {
            str(source.source_collection).removeprefix("Wikipedia category: ")
            for source in sources if str(source.source_collection).startswith("Wikipedia category: ")
        }
        fetched.extend(WikimediaProvider().fetch(min(1000, target + 500), completed_wiki_categories))
        merged = {source.source_url: source for source in sources}
        for source in fetched:
            merged.setdefault(source.source_url, source)
        sources = list(merged.values())
        if len(sources) < target:
            if len(sources) >= len(previous_sources):
                save_source_cache(source_cache, sources)
            raise RuntimeError(f"only {len(sources)} unique approved source records were found; source cache was saved, bank was not changed")
        save_source_cache(source_cache, sources)
    generator, judge = FactScriptGenerator(), ScriptJudge()
    detector = DuplicateDetector(
        settings.title_similarity_threshold,
        settings.hook_similarity_threshold,
        settings.story_similarity_threshold,
    )
    source_by_url = {source.source_url: source for source in sources}
    unused = [source for source in sources if source.source_url not in {str(item.get("source_url")) for item in bank.items}]
    for source in unused:
        if len(bank.items) >= target:
            break
        candidate = generator.generate(source_by_url[source.source_url], len(bank.items))
        quality = judge.score(candidate)
        if not 60 <= int(candidate["word_count"]) <= 100:
            print(f"[{len(bank.items)}/{target}] REJECT - word count {candidate['word_count']}")
        elif quality.total < settings.quality_threshold:
            print(f"[{len(bank.items)}/{target}] REJECT - quality {quality.total}/50")
        else:
            duplicate = detector.check(candidate, bank.items)
            if duplicate.duplicate:
                print(f"[{len(bank.items)}/{target}] REJECT - {duplicate.reason} {duplicate.score:.2f}")
            else:
                script_id = f"HF{len(bank.items) + 1:04d}"
                candidate.update({
                    "id": script_id,
                    "quality_score": quality.total,
                    "quality_breakdown": {
                        "hook": quality.hook, "curiosity": quality.curiosity,
                        "escalation": quality.escalation, "visual_potential": quality.visual_potential,
                        "twist_payoff": quality.twist_payoff,
                    },
                    "similarity_score": 0.0,
                    "status": "ready",
                    "created_at": utc_now(),
                    "used_at": None,
                    "youtube_video_id": None,
                })
                bank.add(candidate)
                print(f"[{len(bank.items)}/{target}] ACCEPT {script_id} - {candidate['category']}")
    if len(bank.items) != target:
        raise RuntimeError(f"could only build {len(bank.items)} of {target} scripts")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or resume the validated horror script bank.")
    parser.add_argument("--target", type=int, default=500)
    parser.add_argument("--bank", type=Path)
    parser.add_argument("--source-cache", type=Path, default=ROOT / "data" / "fact_sources.json")
    parser.add_argument("--refresh-sources", action="store_true")
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        if args.bank:
            settings = Settings.from_env(args.bank.resolve().parents[1])
            object.__setattr__(settings, "bank_path", args.bank.resolve())
        settings.validate()
        return build(args.target, settings, args.source_cache.resolve(), args.refresh_sources)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Bank build failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
