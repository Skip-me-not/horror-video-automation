from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


GAME_TYPES = ("choose_door", "find_ghost", "spot_change", "escape_room", "safe_object", "moving_entity")
SETTINGS = (
    "abandoned hospital", "dark bedroom", "school hallway", "basement", "forest cabin",
    "hotel corridor", "elevator", "underground tunnel", "security camera room",
    "abandoned house", "parking garage", "old bathroom", "empty office",
)
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
        setting = rng.choice(SETTINGS)
        monster = rng.choice(MONSTERS)
        hook = rng.choice(self.hooks[game_type])
        base: dict[str, Any] = {
            "version": 1, "game_type": game_type, "setting": setting, "hook": hook,
            "countdown_seconds": rng.choice((4, 5)), "monster": monster,
        }
        if game_type == "choose_door":
            base.update(choices=[{"id": "A", "label": "LEFT"}, {"id": "B", "label": "RIGHT"}],
                        correct_choice=rng.choice(("A", "B")), reveal="THE OTHER DOOR WAS BREATHING")
        elif game_type == "escape_room":
            base.update(choices=[{"id": "A", "label": "BED"}, {"id": "B", "label": "CLOSET"},
                                 {"id": "C", "label": "WINDOW"}], correct_choice=rng.choice(("A", "B", "C")),
                        reveal=f"THE {monster.upper()} CHECKED THE WRONG PLACE")
        elif game_type == "safe_object":
            labels = rng.sample(OBJECTS, 3)
            base.update(choices=[{"id": chr(65 + index), "label": label} for index, label in enumerate(labels)],
                        correct_choice=rng.choice(("A", "B", "C")), reveal="ONE OBJECT HAS NO REFLECTION")
        elif game_type == "find_ghost":
            base.update(target="FACE IN THE DARK", target_position=[rng.randint(180, 850), rng.randint(520, 1320)],
                        reveal="IT WAS WATCHING THE WHOLE TIME")
        elif game_type == "spot_change":
            base.update(target="THE CLOCK MOVED", target_position=[rng.randint(220, 820), rng.randint(620, 1260)],
                        reveal="THE CLOCK LOST ONE HOUR")
        else:
            base.update(target="ENTITY 03", target_position=[rng.randint(250, 800), rng.randint(600, 1250)],
                        reveal="ENTITY 03 TURNED TOWARD YOU")
        base.update(success_text="YOU SURVIVED", failure_text="IT FOUND YOU")
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
                "success_text", "failure_text"}
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
