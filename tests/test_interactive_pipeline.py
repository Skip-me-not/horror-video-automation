from __future__ import annotations

import json
import random

import pytest

from src.game_generator import GAME_TYPES, GameGenerator, validate_game
from src.history import HistoryStore, sha256_file
from src.metadata import generate_metadata
from src.scene_generator import InteractiveSceneGenerator


@pytest.mark.parametrize("game_type", GAME_TYPES)
def test_all_interactive_game_types_validate(game_type, tmp_path):
    hooks = {kind: [f"HOOK FOR {kind}"] for kind in GAME_TYPES}
    path = tmp_path / "hooks.json"
    path.write_text(json.dumps(hooks), encoding="utf-8")
    game = GameGenerator(path).generate(random.Random(123), game_type)
    validate_game(game)
    phases = InteractiveSceneGenerator().generate_game(game)
    assert phases[0]["kind"] == "hook"
    assert phases[0]["duration"] <= 2
    assert phases[-1]["kind"] == "loop"
    assert 15 <= sum(item["duration"] for item in phases) <= 30


def test_history_limits_and_detects_duplicate(tmp_path):
    store = HistoryStore(tmp_path / "history.json", limit=2)
    store.append({"game_type": "choose_door", "video_hash": "one"})
    store.append({"game_type": "find_ghost", "video_hash": "two"})
    store.append({"game_type": "spot_change", "video_hash": "three"})
    assert len(store.load()) == 2
    assert store.contains_hash("three")
    assert not store.contains_hash("one")


def test_sha256_and_metadata(tmp_path):
    video = tmp_path / "short.mp4"
    video.write_bytes(b"same video")
    assert sha256_file(video) == sha256_file(video)
    metadata = generate_metadata({"game_type": "choose_door"}, "private")
    assert metadata["privacy_status"] == "private"
    assert metadata["category_id"] == "24"
    assert len(metadata["tags"]) <= 5
