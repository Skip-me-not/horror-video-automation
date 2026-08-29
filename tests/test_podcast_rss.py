from src.podcast_rss import is_horror_episode


def test_rss_relevance_rejects_unrelated_entertainment_episode():
    assert not is_horror_episode("Deck The Hallmark", "February Preview Show", "Romance movie previews")


def test_rss_relevance_accepts_haunted_folklore_episode():
    assert is_horror_episode("Ghost Tales", "The Haunted Chapel", "Dark folklore and an apparition")
