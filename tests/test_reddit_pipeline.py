from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.error import HTTPError

import src.reddit_compositor as compositor
import src.reddit_source as reddit_source
from src.reddit_source import RedditVideoPost, build_narration, parse_comment_feed, parse_video_feed


def test_parse_reddit_hosted_video_feed():
    payload = b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><author><name>/u/tester</name></author><content type="html">&lt;!-- SC_OFF --&gt;&lt;div class="md"&gt;&lt;p&gt;People walked through the figure.&lt;/p&gt;&lt;/div&gt;&lt;!-- SC_ON --&gt;&lt;a href="https://v.redd.it/abc123"&gt;[link]&lt;/a&gt;</content><id>t3_post1</id><link href="https://www.reddit.com/r/Ghosts/comments/post1/example/"/><published>2026-01-01T00:00:00Z</published><title>Figure in a hospital</title></entry>
    </feed>'''
    posts = parse_video_feed(payload, "Ghosts")
    assert len(posts) == 1
    assert posts[0].post_id == "post1"
    assert posts[0].video_url == "https://v.redd.it/abc123"
    assert "People walked" in posts[0].body


def test_comment_context_and_narration_are_attributed():
    comment_feed = b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><id>t1_c1</id><content type="html">&lt;div class="md"&gt;&lt;p&gt;That shape stays still while everyone walks past it.&lt;/p&gt;&lt;/div&gt;</content></entry></feed>'''
    comments = parse_comment_feed(comment_feed, "post1")
    post = RedditVideoPost("post1", "Ghosts", "A figure in the hospital", "People walked through him.",
                           "/u/tester", "https://reddit.test/post1", "https://v.redd.it/abc", "", comments)
    result = build_narration(post)
    assert "r Ghosts" in result["narration"]
    assert "tester" in result["narration"]
    assert "comment section" in result["narration"]
    assert result["hook"].startswith("WATCH CLOSELY")
    assert len(result["hook"]) <= 58


def test_subtitle_hook_is_red_and_wraps(tmp_path):
    from src.subtitles import SubtitleWriter
    output = SubtitleWriter().from_timings(
        [{"text": "Something", "offset": 2.8, "duration": 0.4}], tmp_path / "captions.ass",
        hook_text="WATCH THE CENTER OF THE ORIGINAL REDDIT VIDEO", hook_duration=2.8,
    )
    content = output.read_text(encoding="utf-8")
    assert "Style: Hook,DejaVu Sans,78,&H000000FF" in content
    assert r"\N" in content
    assert "Dialogue: 2,0:00:00.00,0:00:02.80,Hook" in content


def test_compositor_normalizes_segment_sample_aspect_ratio(tmp_path, monkeypatch):
    captured: dict[str, list[str]] = {}
    destination = tmp_path / "short.mp4"

    monkeypatch.setattr(compositor, "media_details", lambda _source: (12.0, False))
    monkeypatch.setattr(compositor, "average_luma", lambda _source, _ffmpeg: 48.0)

    def fake_run(command, **_kwargs):
        captured["command"] = command
        destination.write_bytes(b"0" * 500_001)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(compositor, "run", fake_run)
    report = compositor.compose_reddit_short(
        tmp_path / "source.mp4", tmp_path / "voice.mp3", tmp_path / "captions.ass",
        destination, final_duration=8.0, hook_duration=2.8, hook_start=1.0,
    )

    graph = captured["command"][captured["command"].index("-filter_complex") + 1]
    assert graph.count("setsar=1") == report["segment_count"]
    assert "drawtext=textfile=" in graph
    assert "x=(w-text_w)/2:y=h-text_h-180" in graph
    assert (tmp_path / "watermark.txt").read_text(encoding="utf-8") == "SKIP IF YOU'RE SCARED"
    assert report["watermark_text"] == "SKIP IF YOU'RE SCARED"


def test_reddit_fetch_retries_rate_limit(monkeypatch):
    attempts = []
    delays = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"feed"

    def fake_open(*_args, **_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise HTTPError("https://reddit.test", 429, "rate limited", {}, None)
        return Response()

    monkeypatch.setattr(reddit_source, "urlopen", fake_open)
    monkeypatch.setattr(reddit_source.time, "sleep", delays.append)
    assert reddit_source._fetch("https://reddit.test", attempts=2) == b"feed"
    assert len(attempts) == 2
    assert delays == [8.0]


def test_cached_reddit_pool_survives_live_rate_limit(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "config" / "reddit_sources.json").write_text(json.dumps({
        "subreddits": ["Ghosts"], "listing": "top", "period": "month",
        "maximum_feed_attempts": 1, "feed_hosts": ["www.reddit.com"],
        "request_attempts": 1, "refresh_pool_below": 12,
    }), encoding="utf-8")
    (tmp_path / "data" / "reddit_source_pool.json").write_text(json.dumps([{
        "post_id": "cached1", "subreddit": "Ghosts", "title": "Figure in a hospital",
        "body": "People walked through the shadow.", "author": "/u/tester",
        "post_url": "https://www.reddit.com/r/Ghosts/comments/cached1/example/",
        "video_url": "https://v.redd.it/cachedvideo", "published": "2026-01-01T00:00:00Z",
    }]), encoding="utf-8")

    def rate_limited(*_args, **_kwargs):
        raise HTTPError("https://reddit.test", 429, "rate limited", {}, None)

    monkeypatch.setattr(reddit_source, "_fetch", rate_limited)
    posts = reddit_source.discover_video_posts(tmp_path, set(), "seed")
    assert [post.post_id for post in posts] == ["cached1"]


def test_live_reddit_feed_populates_persistent_pool(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "reddit_sources.json").write_text(json.dumps({
        "subreddits": ["Ghosts"], "listing": "top", "period": "month",
        "maximum_feed_attempts": 1, "feed_hosts": ["www.reddit.com"],
        "request_attempts": 1, "refresh_pool_below": 12, "target_pool_size": 24,
        "pool_limit": 120,
    }), encoding="utf-8")
    payload = b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><author><name>/u/tester</name></author><content type="html">&lt;div class="md"&gt;&lt;p&gt;A dark figure moved.&lt;/p&gt;&lt;/div&gt;&lt;a href="https://v.redd.it/newvideo"&gt;[link]&lt;/a&gt;</content><id>t3_new1</id><link href="https://www.reddit.com/r/Ghosts/comments/new1/example/"/><published>2026-01-01T00:00:00Z</published><title>Dark figure</title></entry>
    </feed>'''
    monkeypatch.setattr(reddit_source, "_fetch", lambda *_args, **_kwargs: payload)
    posts = reddit_source.discover_video_posts(tmp_path, set(), "seed")
    saved = json.loads((tmp_path / "data" / "reddit_source_pool.json").read_text(encoding="utf-8"))
    assert [post.post_id for post in posts] == ["new1"]
    assert saved[0]["video_url"] == "https://v.redd.it/newvideo"
