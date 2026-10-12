import pytest

from scripts.reddit_source import (
    RedditClient,
    RedditSourceError,
    normalize_post,
    parse_old_reddit_html,
    parse_reddit_rss,
    parse_subreddits,
    reddit_video_url,
    rank_clip_posts,
    select_clip_posts,
    select_fact_posts,
)
from scripts.render_idol_short import (
    IdolShortError,
    build_metadata,
    build_segments,
    build_word_captions,
    download_clip_pool,
    narration_text,
    reddit_hls_url,
    reddit_manifest_urls,
    word_count,
)


def raw_post(
    post_id: str,
    title: str,
    *,
    score: int = 900,
    comments: int = 120,
    subreddit: str = "kpop",
    video: bool = False,
    over_18: bool = False,
):
    payload = {
        "id": post_id,
        "title": title,
        "author": "source_author",
        "subreddit": subreddit,
        "score": score,
        "num_comments": comments,
        "created_utc": 1_750_000_000,
        "permalink": f"/r/{subreddit}/comments/{post_id}/source/",
        "over_18": over_18,
        "stickied": False,
        "selftext": "",
    }
    if video:
        payload["secure_media"] = {
            "reddit_video": {
                "fallback_url": f"https://v.redd.it/{post_id}/DASH_720.mp4?source=fallback",
                "duration": 18,
            }
        }
    return payload


def normalized_posts():
    return [
        normalize_post(raw_post("a1", "Jungkook became the first K-pop soloist to reach this chart record", score=5400, comments=430, video=True)),
        normalize_post(raw_post("a2", "Jungkook explained why he changed one key part of his live performance", score=3300, comments=280, video=True)),
        normalize_post(raw_post("a3", "Jungkook surprised fans with a detail hidden in his latest stage", score=2400, comments=190, video=True)),
        normalize_post(raw_post("a4", "Jungkook reached another streaming milestone in his debut year", score=1900, comments=160, video=True)),
    ]


def test_subreddit_parser_accepts_common_input_and_rejects_paths():
    assert parse_subreddits("r/kpop, kpopthoughts+kpop_uncensored") == [
        "kpop",
        "kpopthoughts",
        "kpop_uncensored",
    ]
    with pytest.raises(RedditSourceError, match="Invalid subreddit"):
        parse_subreddits("../private")


def test_reddit_client_needs_only_a_public_user_agent():
    client = RedditClient(user_agent="github:shorts-test:v1")
    assert client.user_agent == "github:shorts-test:v1"
    assert not hasattr(client, "client_id")
    assert not hasattr(client, "client_secret")


def test_old_reddit_html_fallback_extracts_fact_and_hosted_video():
    page = """
    <div class="thing link" data-fullname="t3_web1" data-score="725"
         data-permalink="/r/kpop/comments/web1/source/" data-url="https://v.redd.it/clipweb1">
      <a class="title">Jungkook reached a new live performance milestone</a>
      <a class="author">source_author</a>
      <a class="comments may-blank">86 comments</a>
    </div>
    """
    posts = parse_old_reddit_html(page, "kpop")
    assert len(posts) == 1
    assert posts[0]["id"] == "web1"
    assert posts[0]["score"] == 725
    assert posts[0]["num_comments"] == 86
    assert posts[0]["video_url"] == "https://v.redd.it/clipweb1/DASH_720.mp4?source=fallback"


def test_reddit_rss_fallback_extracts_original_post_and_video_links():
    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>t3_rss1</id>
        <title>Jungkook became the first soloist to reach this record</title>
        <link href="https://www.reddit.com/r/kpop/comments/rss1/source/" />
        <content type="html">&lt;a href="https://v.redd.it/cliprss1"&gt;video&lt;/a&gt;</content>
      </entry>
    </feed>"""
    posts = parse_reddit_rss(feed, "kpop")
    assert len(posts) == 1
    assert posts[0]["permalink"] == "/r/kpop/comments/rss1/source/"
    assert posts[0]["score"] == 40
    assert posts[0]["video_url"] == "https://v.redd.it/cliprss1/DASH_720.mp4?source=fallback"


def test_reddit_video_url_accepts_only_reddit_hosted_video():
    safe = raw_post("clip1", "Jungkook live performance", video=True)
    assert reddit_video_url(safe).startswith("https://v.redd.it/")
    assert reddit_hls_url(reddit_video_url(safe)) == "https://v.redd.it/clip1/HLSPlaylist.m3u8"
    assert reddit_manifest_urls(reddit_video_url(safe)) == [
        "https://v.redd.it/clip1/HLSPlaylist.m3u8",
        "https://v.redd.it/clip1/DASHPlaylist.mpd",
    ]
    safe["secure_media"]["reddit_video"]["fallback_url"] = "https://evil.example/clip.mp4"
    assert reddit_video_url(safe) == ""


def test_fact_selection_rejects_rumours_questions_and_nsfw():
    posts = normalized_posts()
    posts.extend(
        [
            normalize_post(raw_post("bad1", "Unconfirmed rumor about Jungkook and a leaked schedule", score=99999)),
            normalize_post(raw_post("bad2", "What do you think Jungkook might announce next?", score=99999)),
            normalize_post(raw_post("bad3", "Jungkook backstage update from the tour", score=99999, over_18=True)),
        ]
    )
    selected = select_fact_posts(posts, "Jungkook", count=4)
    assert {post["id"] for post in selected} == {"a1", "a2", "a3", "a4"}


def test_fact_selection_avoids_used_sources():
    posts = normalized_posts()
    used = "https://www.reddit.com/r/kpop/comments/a1/source/"
    with pytest.raises(RedditSourceError, match="only 3"):
        select_fact_posts(posts, "Jungkook", count=4, excluded_urls=[used])


def test_clip_selection_requires_distinct_safe_reddit_videos():
    posts = normalized_posts()
    ranked = rank_clip_posts(posts, "Jungkook")
    selected = select_clip_posts(posts, "Jungkook", count=4)
    assert len(ranked) == 4
    assert len(selected) == 4
    assert len({post["video_url"] for post in selected}) == 4


def test_download_pool_replaces_a_dead_reddit_clip(tmp_path):
    attempts: list[str] = []

    def fake_downloader(url, destination, *, user_agent):
        attempts.append(url)
        if len(attempts) == 1:
            raise IdolShortError("403 Forbidden")
        destination.write_bytes(b"video" * 3000)

    candidates = rank_clip_posts(normalized_posts(), "Jungkook")
    local_clips, selected = download_clip_pool(
        candidates,
        count=3,
        directory=tmp_path,
        user_agent="test-agent",
        downloader=fake_downloader,
    )

    assert len(attempts) == 4
    assert len(local_clips) == 3
    assert len(selected) == 3
    assert all(path.stat().st_size >= 10_000 for path in local_clips)
    assert attempts[0] not in {post["video_url"] for post in selected}


def test_three_or_four_fact_script_has_hook_numbered_facts_and_cta():
    facts = normalized_posts()
    segments = build_segments("Jungkook", facts)
    script = narration_text(segments)
    assert len(segments) == 6
    assert "4 Jungkook moments" in script
    assert all(f"Number {number}." in script for number in range(1, 5))
    assert "part two" in script
    assert 95 <= word_count(script) <= 180


def test_reference_caption_style_is_one_word_hot_pink_with_emphasis():
    segments = [
        {"kind": "hook", "text": "Three rich idols reached one million views."},
        {"kind": "outro", "text": "Follow for part two."},
    ]
    captions = build_word_captions(segments, 8.0)
    assert captions.count("Dialogue: 2,") == word_count(narration_text(segments))
    assert r"\pos(540,1120)" in captions
    assert "&H00AE3DFF" in captions
    assert "&H003DE6FF" in captions
    assert "Poppins SemiBold,62" in captions


def test_public_metadata_records_automatic_publication_mode():
    posts = normalized_posts()
    segments = build_segments("Jungkook", posts)
    metadata = build_metadata(
        "Jungkook",
        posts,
        posts,
        segments,
        duration=58.5,
        privacy="public",
        music={
            "title": "Pop Beat",
            "creator": "Music Creator",
            "license": "CC0",
            "source_url": "https://openverse.org/audio/example",
        },
        voice={
            "name": "en_US-joe-medium",
            "license": "CC0 voice dataset",
            "source_url": "https://example.com/voice",
        },
        channel_name="ORDERLESS",
    )
    assert metadata["privacy_status"] == "public"
    assert metadata["publication_mode"] == "automatic_public"


def test_metadata_records_reddit_sources_and_review_status():
    posts = normalized_posts()
    segments = build_segments("Jungkook", posts)
    music = {
        "title": "Pop Beat",
        "creator": "Music Creator",
        "license": "CC0",
        "source_url": "https://openverse.org/audio/example",
    }
    voice = {
        "name": "en_US-joe-medium",
        "license": "CC0 voice dataset",
        "source_url": "https://example.com/voice",
    }
    metadata = build_metadata(
        "Jungkook",
        posts,
        posts,
        segments,
        duration=58.5,
        privacy="public",
        music=music,
        voice=voice,
        channel_name="ORDERLESS",
    )
    assert metadata["format"] == "ai_reddit_idol_short"
    assert metadata["script_engine"] == "legacy_editorial"
    assert metadata["publication_mode"] == "automatic_public"
    assert metadata["fact_count"] == 4
    assert len(metadata["fact_sources"]) == 4
    assert len(metadata["clip_sources"]) == 4
    assert metadata["privacy_status"] == "public"
    assert metadata["publication_mode"] == "automatic_public"
    assert "source attribution" in metadata["fact_verification"]



def test_reddit_rotation_merge_preserves_concurrent_sources():
    from scripts.merge_reddit_state import merge_states

    current = {
        "version": 1,
        "used_fact_urls": ["https://www.reddit.com/fact-a"],
        "used_clip_urls": ["https://www.reddit.com/clip-a"],
        "idol_history": ["Jennie"],
    }
    rendered = {
        "version": 1,
        "used_fact_urls": ["https://www.reddit.com/fact-b"],
        "used_clip_urls": ["https://www.reddit.com/clip-b"],
        "idol_history": ["Jungkook"],
    }
    merged = merge_states(current, rendered)
    assert merged["used_fact_urls"] == [
        "https://www.reddit.com/fact-a",
        "https://www.reddit.com/fact-b",
    ]
    assert merged["used_clip_urls"] == [
        "https://www.reddit.com/clip-a",
        "https://www.reddit.com/clip-b",
    ]
    assert merged["idol_history"] == ["Jennie", "Jungkook"]
