from scripts.editorial_script import generate_editorial_script


def facts():
    return [
        {"title": f"Jungkook source detail number {index} became a fan discussion", "subreddit": "bts7", "score": 1000 + index * 100, "num_comments": 100 + index * 10}
        for index in range(1, 5)
    ]


def test_deterministic_script_has_hook_fact_beats_and_cta():
    result = generate_editorial_script("Jungkook", facts())
    assert result.engine == "editorial_deterministic"
    assert result.model == "none"
    assert len(result.segments) == 6
    assert result.segments[0]["kind"] == "hook"
    assert [segment["fact_number"] for segment in result.segments[1:-1]] == [1, 2, 3, 4]
    assert result.segments[-1]["kind"] == "outro"
    assert 95 <= len(result.narration.split()) <= 180


def test_same_sources_produce_same_script():
    first = generate_editorial_script("Jungkook", facts())
    second = generate_editorial_script("Jungkook", facts())
    assert first.segments == second.segments
