from __future__ import annotations

import argparse
import json
from pathlib import Path


SETTINGS = [
    ("abandoned hospital", "an abandoned hospital corridor", "empty abandoned hospital corridor"),
    ("subway station", "the last underground station", "empty dark subway station"),
    ("forest cabin", "a locked cabin deep in the woods", "empty haunted forest cabin"),
    ("old hotel", "the condemned top floor of an old hotel", "empty abandoned hotel corridor"),
    ("school", "a school closed for the summer", "empty dark abandoned school hallway"),
    ("farmhouse", "an isolated farmhouse during a storm", "empty haunted farmhouse interior"),
    ("parking garage", "the lowest level of an empty parking garage", "empty dark parking garage"),
    ("lighthouse", "a lighthouse cut off by the tide", "empty haunted lighthouse interior"),
    ("apartment", "an apartment building marked for demolition", "empty abandoned apartment hallway"),
    ("church", "a ruined church after midnight", "empty ruined church interior"),
]

THREATS = [
    ("whisper", "the emergency speaker whispered their childhood nickname", "the whisper answered from inside the locked wall"),
    ("footsteps", "wet footsteps followed one pace behind", "the footsteps continued after they stopped moving"),
    ("reflection", "every reflection moved a second too late", "the reflection smiled while their real face stayed still"),
    ("telephone", "a disconnected telephone began ringing", "the caller calmly described what was standing behind them"),
    ("door", "a door appeared where the wall had always been solid", "something on the other side knocked in the rhythm of their heartbeat"),
    ("photograph", "a dusty photograph showed them already inside the room", "each new picture placed the dark figure closer"),
    ("elevator", "the elevator opened onto a floor missing from every plan", "the display counted below zero as the doors closed"),
    ("radio", "a dead radio broadcast tomorrow's missing-person report", "the announcer used their voice to read the final name"),
    ("shadow", "their shadow turned the opposite direction", "it reached the exit several seconds before they did"),
    ("camera", "the security camera showed an extra shape beside them", "the shape vanished from the screen and breathed beside the lens"),
]

ENDINGS = [
    ("loop", "They ran for the exit and entered the same room again, where another version of them was just beginning the night."),
    ("replacement", "At dawn, they walked outside smiling, but the thing behind their eyes no longer knew how to blink."),
    ("warning", "Their phone sent one final message to every contact: if you hear me calling tonight, do not answer."),
    ("recording", "Police found only a recording that ended with their voice whispering from somewhere beneath the floor."),
    ("arrival", "Then the lights returned, revealing hundreds of fresh footprints all pointing toward them."),
]

NAMES = ["Alex", "Mara", "Eli", "Nora", "Jonah", "Claire", "Miles", "Iris", "Theo", "June"]


def build_ideas() -> list[dict[str, object]]:
    ideas: list[dict[str, object]] = []
    number = 1
    for setting_index, (setting_name, setting, query) in enumerate(SETTINGS):
        for threat_index, (threat_name, opening, reveal) in enumerate(THREATS):
            for ending_name, ending in ENDINGS:
                name = NAMES[(setting_index + threat_index + number) % len(NAMES)]
                story = (
                    f"At 2:13 a.m., {name} was alone in {setting}. "
                    f"Without warning, {opening}. {name} checked every entrance, but all of them were still locked. "
                    f"Then {reveal}. {ending}"
                )
                ideas.append({
                    "idea_number": number,
                    "title": f"The {threat_name.title()} in the {setting_name.title()} — {ending_name.title()}",
                    "story": story,
                    "description": "An original 30-second English horror story.",
                    "tags": ["horror shorts", "scary stories", "creepy stories", "shorts"],
                    "background_file": "dark-corridor.png",
                    "background_query": query,
                    "watermark_text": "SKIP IF YOU'RE SCARED",
                })
                number += 1
    return ideas


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the replaceable 500-story horror idea bank.")
    parser.add_argument("--output", default="ideas/horror-ideas-500.json")
    args = parser.parse_args()
    ideas = build_ideas()
    if len(ideas) != 500:
        raise RuntimeError(f"expected 500 ideas, generated {len(ideas)}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ideas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(ideas)} ideas to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
