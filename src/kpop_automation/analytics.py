from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def collect_snapshot(state: dict[str, Any], destination: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    unavailable = "YouTube read/analytics permission is not configured"
    try:
        from googleapiclient.discovery import build
        from scripts.upload_youtube import credentials_from_environment
        youtube = build("youtube", "v3", credentials=credentials_from_environment(), cache_discovery=False)
        ids = [item.get("youtube_video_id") for item in state.get("uploads", {}).values() if item.get("youtube_video_id")]
        for offset in range(0, len(ids), 50):
            response = youtube.videos().list(part="statistics,snippet", id=",".join(ids[offset:offset + 50])).execute()
            for item in response.get("items", []):
                stats = item.get("statistics", {})
                rows.append({"video_id": item["id"], "title": item["snippet"]["title"],
                             "views": stats.get("viewCount"), "likes": stats.get("likeCount"),
                             "comments": stats.get("commentCount"), "watch_time": None,
                             "average_view_duration": None, "subscribers_gained": None})
        unavailable = "YouTube Analytics-only metrics unavailable with current OAuth scope"
    except Exception as exc:
        unavailable = str(exc)
    destination.mkdir(parents=True, exist_ok=True)
    snapshot = {"captured_at": datetime.now(timezone.utc).isoformat(), "rows": rows,
                "unavailable_metrics_note": unavailable}
    (destination / "analytics.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    fields = ["video_id", "title", "views", "likes", "comments", "watch_time", "average_view_duration", "subscribers_gained"]
    with (destination / "analytics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    markdown = ["# Lululala performance dashboard", "", f"Captured: {snapshot['captured_at']}", "",
                "Comparable-age analysis requires multiple snapshots; no conclusion is drawn from one outlier.", "",
                f"Unavailable: {unavailable}", "", f"Videos recorded: {len(rows)}"]
    (destination / "DASHBOARD.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return snapshot
