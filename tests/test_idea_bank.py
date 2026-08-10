import json
from pathlib import Path

import pytest

from scripts.build_job_from_idea import build_job, select_idea
from scripts.common import ValidationError, load_config
from scripts.generate_idea_bank import build_ideas
from scripts.validate_job import validate_job


def test_idea_bank_is_genre_balanced_and_valid():
    ideas = build_ideas()
    config = load_config("config/default.json")
    assert len(ideas) == 180
    assert len({idea["title"] for idea in ideas}) == 180
    assert len({idea["genre"] for idea in ideas}) == 15
    assert max(len(idea["story"]) for idea in ideas) - min(len(idea["story"]) for idea in ideas) > 300
    assert [idea["idea_number"] for idea in ideas] == list(range(1, 181))
    for idea in ideas:
        validate_job(build_job(idea, f"idea-{idea['idea_number']:03d}"), config)


def test_committed_bank_matches_generator():
    committed = json.loads(Path("ideas/horror-stories.json").read_text(encoding="utf-8"))
    assert committed == build_ideas()


def test_idea_number_must_be_in_range():
    with pytest.raises(ValidationError, match="between 1 and 1"):
        select_idea([{"idea_number": 1}], 2)
