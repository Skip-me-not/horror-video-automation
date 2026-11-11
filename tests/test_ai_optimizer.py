import json
from unittest.mock import Mock

import pytest

from scripts.ai_optimizer import AIOptimizationError, optimize_packaging, validate_optimization


def stories():
    return [
        {
            "story_id": f"reddit-{index}",
            "ranked_topic": "Jennie",
            "headline": f"Jennie moment {index} from a public fan video",
            "source_name": "r/BlackPink",
            "reddit_score": 1000 - index,
            "reddit_comments": 100 - index,
            "date": "2026-11-05",
        }
        for index in range(6)
    ]


def valid_payload():
    return {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "title": "The Jennie Moment Fans Kept Replaying",
                    "hook": "Jennie's most-upvoted moment leads this countdown",
                    "subtitle": "Six Jennie moments ranked by fan discussion",
                    "cta": "Was Jennie number one the right choice?",
                })
            }
        }]
    }


def test_optimizer_uses_one_structured_low_token_request():
    session = Mock()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = valid_payload()
    session.post.return_value = response

    result = optimize_packaging(stories(), token="github-token", mode="required", session=session)

    assert result.engine == "github_models"
    assert result.model == "openai/gpt-4o-mini"
    assert result.title.startswith("The Jennie")
    request = session.post.call_args.kwargs["json"]
    assert request["max_tokens"] == 220
    assert request["response_format"] == {"type": "json_object"}
    assert len(request["messages"]) == 2


def test_auto_mode_falls_back_without_a_token():
    result = optimize_packaging(stories(), mode="auto")
    assert result.engine == "deterministic_fallback"
    assert result.title == "6 Jennie Moments Fans Ranked Highest"


def test_required_mode_rejects_invalid_model_output():
    with pytest.raises(AIOptimizationError, match="title"):
        validate_optimization({"title": "bad", "hook": "too short", "subtitle": "Jennie", "cta": "Comment"}, "Jennie")


def test_auto_mode_falls_back_when_model_times_out():
    session = Mock()
    session.post.side_effect = TimeoutError("model unavailable")
    result = optimize_packaging(stories(), token="github-token", mode="auto", session=session)
    assert result.engine == "deterministic_fallback"
    assert result.cta == "WHO SHOULD WE RANK NEXT?"
