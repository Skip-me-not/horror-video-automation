from scripts.merge_reddit_state import merge_history, merge_pool


def test_concurrent_history_is_merged_without_duplicate_sources():
    remote = [{"source_video_id": "remote", "youtube_video_id": "yt-remote"}]
    incoming = [
        {"source_video_id": "remote", "youtube_video_id": "duplicate"},
        {"source_video_id": "incoming", "youtube_video_id": "yt-incoming"},
    ]
    merged = merge_history(remote, incoming)
    assert {item["source_video_id"] for item in merged} == {"remote", "incoming"}
    assert next(item for item in merged if item["source_video_id"] == "remote")["youtube_video_id"] == "duplicate"


def test_used_sources_are_removed_from_merged_pool():
    remote = [{"post_id": "used"}, {"post_id": "remote"}]
    incoming = [{"post_id": "incoming"}, {"post_id": "remote", "title": "newer"}]
    merged = merge_pool(remote, incoming, {"used"})
    assert [item["post_id"] for item in merged] == ["remote", "incoming"]
    assert next(item for item in merged if item["post_id"] == "remote")["title"] == "newer"
