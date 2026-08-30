from __future__ import annotations

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
