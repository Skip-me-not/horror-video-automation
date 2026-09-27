from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .analytics import collect_snapshot
from .pipeline import produce, render_pending
from .state import atomic_write, finalize_upload, load_state
from .telegram import notify


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "kpop.yaml"


def _slot_default() -> str:
    try:
        zone = ZoneInfo("Asia/Yangon")
    except ZoneInfoNotFoundError:
        zone = timezone(timedelta(hours=6, minutes=30), name="Asia/Yangon")
    now = datetime.now(zone)
    return now.strftime("%Y-%m-%dT%H:%M")


def main() -> int:
    parser = argparse.ArgumentParser(prog="lululala")
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("produce")
    make.add_argument("--config", type=Path, default=CONFIG)
    make.add_argument("--slot", default=_slot_default())
    make.add_argument("--category", default="")
    make.add_argument("--dry-run", action="store_true")
    make.add_argument("--fixture", type=Path)
    approve = sub.add_parser("render-pending")
    approve.add_argument("content_id")
    approve.add_argument("--config", type=Path, default=CONFIG)
    final = sub.add_parser("finalize-upload")
    final.add_argument("content_id")
    final.add_argument("--result", type=Path, default=ROOT / "output" / "upload-result.json")
    reject = sub.add_parser("reject")
    reject.add_argument("content_id")
    reject.add_argument("--reason", required=True)
    analytics = sub.add_parser("analytics")
    analytics.add_argument("--output", type=Path, default=ROOT / "reports")
    notice = sub.add_parser("notify")
    notice.add_argument("message")
    args = parser.parse_args()
    if args.command == "produce":
        result = produce(ROOT, args.config, args.slot, args.category, args.dry_run, args.fixture)
        print(json.dumps(result, indent=2)); return 0
    if args.command == "render-pending":
        manifest = render_pending(ROOT, args.config, args.content_id)
        print(json.dumps({"content_id": args.content_id, "status": manifest["status"]}, indent=2)); return 0
    state_path = ROOT / "data" / "kpop_state.json"
    state = load_state(state_path)
    if args.command == "finalize-upload":
        result = json.loads(args.result.read_text(encoding="utf-8"))
        if result.get("status") != "success" or not result.get("youtube_video_id"):
            raise ValueError("YouTube API did not confirm a successful upload")
        finalize_upload(state, args.content_id, result); atomic_write(state_path, state)
        history = []
        for video_id, item in state["uploads"].items():
            manifest_path = ROOT / "data" / "manifests" / f"{video_id}.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
            sources = manifest.get("topic", {}).get("sources", [])
            history.append({"video_id": video_id, "topic": manifest.get("topic", {}).get("title", ""),
                            "celebrity": manifest.get("topic", {}).get("entity", ""),
                            "source_url": sources[0].get("url", "") if sources else "",
                            "published_at": sources[0].get("published_at", "") if sources else "",
                            "uploaded_at": item.get("recorded_at", ""),
                            "youtube_video_id": item.get("youtube_video_id", ""),
                            "title": manifest.get("script", {}).get("title", "")})
        atomic_write(ROOT / "data" / "upload_history.json", history)
        notify(f"Lululala upload confirmed: {result['watch_url']}")
        return 0
    if args.command == "reject":
        if args.content_id not in state["pending"]:
            raise KeyError("pending content not found")
        state["pending"][args.content_id].update({"status": "rejected", "reason": args.reason})
        atomic_write(state_path, state); return 0
    if args.command == "analytics":
        print(json.dumps(collect_snapshot(state, args.output), indent=2)); return 0
    if args.command == "notify":
        notify(args.message); return 0
    return 2


if __name__ == "__main__":
    (ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}',
                        handlers=[logging.FileHandler(ROOT / "logs" / "automation.log", encoding="utf-8")])
    try:
        raise SystemExit(main())
    except Exception:
        logging.exception("pipeline failed")
        raise
