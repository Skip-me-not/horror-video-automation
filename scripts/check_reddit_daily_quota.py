"""Gate scheduled celebrity uploads against the Myanmar-local daily target."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


# Myanmar does not observe daylight saving time; a fixed offset also works on
# Windows Python installations that do not bundle the IANA tzdata database.
YANGON = timezone(timedelta(hours=6, minutes=30))
ROOT = Path(__file__).resolve().parents[1]


def published_today(records: list[dict], now: datetime) -> int:
    local_day = now.astimezone(YANGON).date()
    count = 0
    for record in records:
        if record.get("source_type") != "reddit-celebrity-video" or not record.get("youtube_video_id"):
            continue
        try:
            recorded = datetime.fromisoformat(str(record["timestamp"]).replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            continue
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)
        if recorded.astimezone(YANGON).date() == local_day:
            count += 1
    return count


def main() -> None:
    records = json.loads((ROOT / "data" / "history.json").read_text(encoding="utf-8"))
    count = published_today(records, datetime.now(timezone.utc))
    manual = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
    should_run = manual or count < 4
    print(f"Myanmar-local celebrity Shorts published today: {count}/4; render={should_run}")
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"should_run={str(should_run).lower()}\n")
            stream.write(f"published_count={count}\n")


if __name__ == "__main__":
    main()
