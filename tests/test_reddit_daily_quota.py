from __future__ import annotations

from datetime import datetime, timezone

from scripts.check_reddit_daily_quota import published_today


def test_yangon_day_boundary_and_only_confirmed_celebrity_uploads_count():
    now = datetime(2026, 10, 4, 16, 0, tzinfo=timezone.utc)  # 22:30 in Myanmar
    records = [
        {"timestamp": "2026-10-03T17:29:59+00:00", "source_type": "reddit-celebrity-video",
         "youtube_video_id": "previous-day"},
        {"timestamp": "2026-10-03T17:30:00+00:00", "source_type": "reddit-celebrity-video",
         "youtube_video_id": "first-today"},
        {"timestamp": "2026-10-04T15:00:00Z", "source_type": "reddit-celebrity-video",
         "youtube_video_id": "second-today"},
        {"timestamp": "2026-10-04T12:00:00+00:00", "source_type": "reddit-celebrity-video"},
        {"timestamp": "2026-10-04T12:00:00+00:00", "source_type": "other",
         "youtube_video_id": "not-celebrity"},
    ]
    assert published_today(records, now) == 2
