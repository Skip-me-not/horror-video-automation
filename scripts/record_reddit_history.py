from __future__ import annotations

import json
from pathlib import Path

from src.history import HistoryStore


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    source = json.loads((root / "output" / "source_info.json").read_text(encoding="utf-8"))
    upload = json.loads((root / "output" / "upload-result.json").read_text(encoding="utf-8"))
    HistoryStore(root / "data" / "history.json", limit=300).append({
        "source_video_id": source["video_id"], "source_url": source["source_url"],
        "source_type": "reddit-video", "youtube_video_id": upload["youtube_video_id"],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
