import json
from unittest.mock import Mock

import pytest

from scripts.ai_script import AIScriptError, generate_script, source_packet, validate_script


def sources():
    return [
        {
            "id": "a1",
            "title": "Jungkook became the first K-pop soloist to reach this chart record",
            "subreddit": "bts7",
            "score": 5400,
            "num_comments": 430,
        },
        {
            "id": "a2",
            "title": "Jungkook explained why he changed one key part of his live performance",
            "subreddit": "kpop",
            "score": 3300,
            "num_comments": 280,
        },
        {
            "id": "a3",
            "title": "Jungkook surprised fans with a detail hidden in his latest stage",
            "subreddit": "kpopthoughts",
            "score": 2400,
            "num_comments": 190,
        },
        {
            "id": "a4",
            "title": "Jungkook reached another streaming milestone in his debut year",
            "subreddit": "bts7",
            "score": 1900,
            "num_comments": 160,
        },
    ]


def valid_model_payload():
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "hook": "Jungkook has four moments where the detail mattered more than the headline.",
                            "facts": [
                                {"text": "First, one chart milestone changed how fans described his solo run and made the achievement feel bigger than a simple number."},
                                {"text": "Second, a small performance change gave viewers a clue about how carefully he approaches a live stage."},
                                {"text": "Third, one hidden detail turned an ordinary comeback moment into a lively debate across several fan communities and comment threads."},
                                {"text": "Fourth, the streaming milestone showed how quickly a release can move from personal project to shared fan event."},
                            ],
                            "outro": "Which Jungkook detail deserves a closer look next? Comment it below and follow for another source-backed story.",
                        }
                    )
                }
            }
        ]
    }


def test_source_packet_contains_only_editorial_source_signals():
    packet = source_packet(sources())
    assert packet[0] == {
        "source_id": "a1",
        "title": sources()[0]["title"],
        "subreddit": "bts7",
        "score": 5400,
        "comments": 430,
    }
    assert "selftext" not in packet[0]


def test_generate_script_uses_structured_model_response():
    session = Mock()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = valid_model_payload()
    session.post.return_value = response

    result = generate_script(
        "Jungkook",
        sources(),
        token="github-token",
        mode="required",
        session=session,
    )

    assert result.engine == "github_models"
    assert result.model == "openai/gpt-4o-mini"
    assert len(result.segments) == 6
    assert result.segments[0]["kind"] == "hook"
    assert result.segments[-1]["kind"] == "outro"
    assert all(segment["kind"] == "fact" for segment in result.segments[1:-1])
    assert session.post.call_args.kwargs["json"]["response_format"] == {"type": "json_object"}


def test_auto_mode_falls_back_without_reading_titles_as_the_whole_script():
    session = Mock()
    session.post.side_effect = TimeoutError("model unavailable")
    result = generate_script("Jungkook", sources(), token="github-token", session=session)
    assert result.engine == "editorial_fallback"
    assert len(result.segments) == 6
    assert result.segments[0]["text"].startswith("4 details about Jungkook")
    assert "Reddit conversation" in result.segments[-1]["text"]


def test_required_mode_rejects_invalid_model_output():
    with pytest.raises(AIScriptError, match="exactly 4 fact beats"):
        validate_script({"hook": "A Jungkook hook that is long enough to pass", "facts": [], "outro": "A sufficiently long closing call to action for viewers."}, "Jungkook", 4)


def test_fallback_mode_never_needs_a_token():
    result = generate_script("Jungkook", sources(), mode="fallback")
    assert result.engine == "editorial_fallback"
    assert 95 <= sum(len(segment["text"].split()) for segment in result.segments) <= 180
