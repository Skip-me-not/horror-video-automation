from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def build_job(source: dict, hook: dict) -> dict:
    title = str(source.get("title") or hook.get("text") or "A Disturbing Horror Podcast Moment")
    channel = str(source.get("channel") or "the original podcast")
    source_url = str(source.get("source_url") or "")
    description = (
        f"A disturbing moment from {channel}: {title}.\n\n"
        + (f"Original source: {source_url}\n\n" if source_url else "")
        + "Listen closely—and tell us what you think happened."
    )
    return {
        "job_id": os.getenv("GITHUB_RUN_ID", "local-podcast-upload"),
        "title": title,
        "description": description,
        "tags": ["horror", "scary stories", "creepy", "ghost stories", "podcast", "shorts"],
        "thumbnail_file": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="output/source_info.json")
    parser.add_argument("--hook", default="output/hook.json")
    parser.add_argument("--output", default="output/upload-job.json")
    args = parser.parse_args()
    source = json.loads(Path(args.source).read_text(encoding="utf-8"))
    hook = json.loads(Path(args.hook).read_text(encoding="utf-8"))
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build_job(source, hook), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
