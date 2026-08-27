from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


GAME_TYPES = ("choose_door", "find_ghost", "spot_change", "escape_room", "safe_object", "moving_entity")
SETTINGS_BY_GAME = {
    "choose_door": ("abandoned hospital", "hotel corridor", "underground tunnel"),
    "find_ghost": ("dark bedroom", "abandoned house", "old bathroom"),
    "spot_change": ("dark bedroom", "abandoned house", "empty office"),
    "escape_room": ("dark bedroom", "basement", "forest cabin"),
    "safe_object": ("dark bedroom", "abandoned house", "old bathroom"),
    "moving_entity": ("parking garage", "security camera room", "underground tunnel"),
}
MONSTERS = ("shadow creature", "pale watcher", "faceless nurse", "ceiling crawler", "mirror figure")
OBJECTS = ("DOLL", "MIRROR", "KEY", "PHONE", "MASK", "CLOCK")


class GameGenerator:
    def __init__(self, hooks_path: Path, history_signatures: set[tuple[str, str, str]] | None = None) -> None:
        self.hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.history_signatures = history_signatures or set()

    def generate(self, rng: random.Random, requested_type: str | None = None) -> dict[str, Any]:
        game_type = requested_type or rng.choice(GAME_TYPES)
        if game_type not in GAME_TYPES:
            raise ValueError(f"unsupported game type: {game_type}")
        for _ in range(30):
            game = self._build(game_type, rng)
            signature = (game_type, game["setting"], game["hook"])
            if signature not in self.history_signatures:
                validate_game(game)
                return game
        game = self.fallback(game_type)
        validate_game(game)
        return game

    def _build(self, game_type: str, rng: random.Random) -> dict[str, Any]:
        setting = rng.choice(SETTINGS_BY_GAME[game_type])
        monster = rng.choice(MONSTERS)
        hook = rng.choice(self.hooks[game_type])
        base: dict[str, Any] = {
            "version": 1, "game_type": game_type, "setting": setting, "hook": hook,
            "countdown_seconds": rng.choice((4, 5)), "monster": monster,
            "level": rng.randint(1, 9), "cold_open": rng.choice((
                "DON'T BLINK.", "IT ALREADY SAW YOU.", "MAKE ONE CHOICE.", "YOU GET ONE CHANCE.",
            )),
        }
        if game_type == "choose_door":
            correct = rng.choice(("A", "B"))
            wrong = "B" if correct == "A" else "A"
            base.update(choices=[{"id": "A", "label": "LEFT"}, {"id": "B", "label": "RIGHT"}],
                        correct_choice=correct, reveal=f"DOOR {correct} WAS SAFE",
                        failure_text=f"PICKED {wrong}? DON'T TURN AROUND.")
        elif game_type == "escape_room":
            correct = rng.choice(("A", "B", "C"))
            base.update(choices=[{"id": "A", "label": "BED"}, {"id": "B", "label": "CLOSET"},
                                 {"id": "C", "label": "WINDOW"}], correct_choice=correct,
                        reveal=f"{correct} WAS THE ONLY SAFE PLACE",
                        failure_text=f"THE {monster.upper()} CHECKED THE OTHERS FIRST")
        elif game_type == "safe_object":
            labels = rng.sample(OBJECTS, 3)
            correct = rng.choice(("A", "B", "C"))
            safe_label = labels[ord(correct) - 65]
            base.update(choices=[{"id": chr(65 + index), "label": label} for index, label in enumerate(labels)],
                        correct_choice=correct, reveal=f"{safe_label} WAS THE ONLY SAFE OBJECT",
                        failure_text="THE OTHER OBJECTS KNOW YOUR NAME")
        elif game_type == "find_ghost":
            # The original bedroom plate contains a naturally concealed figure in
            # the closet. Anchor the game to it instead of drawing a fake sticker.
            base.update(target="SHADOW BY THE CLOSET", target_position=[650, 965],
                        reveal="THE SHADOW WAS BY THE CLOSET",
                        failure_text="MISSED IT? IT MOVED CLOSER")
        elif game_type == "spot_change":
            change = rng.choice((("THE MIRROR CRACKED", [790, 1030]), ("THE DOLL TURNED", [755, 1040]),
                                 ("THE PHONE MOVED", [650, 1060])))
            base.update(target=change[0], target_position=change[1],
                        reveal=change[0], failure_text="IT CHANGED WHILE YOU WERE READING")
        else:
            entity = rng.choice(("01", "02", "03"))
            positions = {"01": [265, 965], "02": [580, 1050], "03": [870, 950]}
            base.update(target=f"ENTITY {entity}", target_position=positions[entity],
                        reveal=f"ENTITY {entity} TURNED TOWARD YOU",
                        failure_text="IT MOVED BEFORE THE TIMER STARTED")
        base.setdefault("failure_text", "IT FOUND YOU")
        base.update(success_text="YOU SURVIVED THIS ROUND",
                    loop_text=rng.choice(("REPLAY. IT MOVED EARLIER.", "WATCH AGAIN—TRUST YOUR FIRST CHOICE.",
                                          "DID YOU SEE THE SECOND THING?")))
        return base

    @staticmethod
    def fallback(game_type: str) -> dict[str, Any]:
        rng = random.Random(f"fallback:{game_type}")
        hooks = {kind: ["CHOOSE NOW."] for kind in GAME_TYPES}
        generator = GameGenerator.__new__(GameGenerator)
        generator.hooks = hooks
        generator.history_signatures = set()
        return generator._build(game_type, rng)


def validate_game(game: dict[str, Any]) -> None:
    required = {"game_type", "setting", "hook", "countdown_seconds", "monster", "reveal",
                "success_text", "failure_text", "cold_open", "loop_text", "level"}
    missing = required - game.keys()
    if missing:
        raise ValueError(f"game JSON missing: {', '.join(sorted(missing))}")
    if game["game_type"] not in GAME_TYPES:
        raise ValueError("invalid game_type")
    if not 3 <= int(game["countdown_seconds"]) <= 6:
        raise ValueError("countdown_seconds must be 3-6")
    if game["game_type"] in {"choose_door", "escape_room", "safe_object"}:
        choices = game.get("choices")
        if not isinstance(choices, list) or len(choices) < 2:
            raise ValueError("choice game requires at least two choices")
        ids = {choice.get("id") for choice in choices}
        if game.get("correct_choice") not in ids:
            raise ValueError("correct_choice must reference a choice")
    else:
        position = game.get("target_position")
        if not isinstance(position, list) or len(position) != 2:
            raise ValueError("visual search game requires target_position")
