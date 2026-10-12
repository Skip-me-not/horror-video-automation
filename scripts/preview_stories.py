#!/usr/bin/env python3
"""Print representative micro-stories without downloading media or uploading."""

from __future__ import annotations

import argparse
import json

from scripts.render_short import STORIES_PATH
from scripts.story_engine import (
    estimate_beat_durations,
    load_stories,
    select_hook,
    select_title,
    story_beats,
    story_script,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=3)
    args = parser.parse_args()
    catalog = load_stories(STORIES_PATH)
    examples = []
    seen_pillars: set[str] = set()
    for story in catalog:
        if story["pillar"] in seen_pillars:
            continue
        hook = select_hook(story)
        beats = story_beats(story, hook)
        examples.append(
            {
                "id": story["id"],
                "pillar": story["pillar"],
                "perspective": story["perspective"],
                "topic": story["topic"],
                "hook": hook,
                "title": select_title(story),
                "estimated_seconds": round(sum(estimate_beat_durations(beats)), 2),
                "script": story_script(story, hook),
                "visual_searches": [beat["visual_search"] for beat in beats],
            }
        )
        seen_pillars.add(story["pillar"])
        if len(examples) == args.count:
            break
    print(json.dumps(examples, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

