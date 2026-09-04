from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .downloader import download_reddit_video
from .history import HistoryStore
from .reddit_compositor import average_luma, compose_reddit_short, find_hook_start, media_details
from .reddit_source import build_narration, discover_video_posts, enrich_with_comments
from .subtitles import SubtitleWriter
from .tts import EdgeTTSNarrator, audio_duration
from .utils import write_json
from .validator import validate_story_short


def run() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    output = root / "output"
    run_dir = Path(os.getenv("RUNNER_TEMP") or root / "temp") / "lululala-celebrity" / os.getenv("GITHUB_RUN_ID", "local")
    output.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    log = output / "processing.log"
    log.write_text("", encoding="utf-8")

    def note(message: str) -> None:
        print(message)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(f"[{datetime.now(timezone.utc).isoformat()}] {message}\n")

    seed = os.getenv("GITHUB_RUN_ID", f"local-{os.getpid()}")
    history = HistoryStore(root / "data" / "history.json", limit=300)
    candidates = discover_video_posts(root, history.used_source_ids(), seed)
    config = json.loads((root / "config" / "reddit_sources.json").read_text(encoding="utf-8"))
    maximum_video_attempts = min(len(candidates), int(config.get("maximum_video_attempts", 8)))
    post = None
    source = None
    source_duration = 0.0
    rejections: list[str] = []
    for index, candidate in enumerate(candidates[:maximum_video_attempts], start=1):
        note(f"Checking Reddit video {index}/{maximum_video_attempts} from r/{candidate.subreddit}: {candidate.title}")
        try:
            media = download_reddit_video(candidate.post_url, run_dir / f"source-{index}", 1080,
                                          direct_video_url=candidate.video_url)
            attempted_source = Path(media["video"])
            attempted_duration, _ = media_details(attempted_source)
            luma = average_luma(attempted_source)
            if attempted_duration < 3.2:
                raise RuntimeError("video shorter than 3.2 seconds")
            if luma < 18.0:
                raise RuntimeError(f"video is visually too dark (average luma {luma:.1f})")
            post, source, source_duration = candidate, attempted_source, attempted_duration
            break
        except Exception as exc:
            rejections.append(f"{candidate.post_id}: {exc}")
            note(f"Rejected source before narration: {exc}")
    if post is None or source is None:
        raise RuntimeError("no visually usable Reddit video passed quality checks: " + " | ".join(rejections))
    post = enrich_with_comments(post)
    script = build_narration(post, int(config.get("target_narration_words", 125)))
    note(f"Selected Reddit video r/{post.subreddit}: {post.title}")

    narration = output / "narration.mp3"
    timing_path = output / "word-timings.json"
    timings = EdgeTTSNarrator("en-US-AvaMultilingualNeural", "+5%").synthesize(
        str(script["narration"]), narration, timing_path,
    )
    hook_duration = 2.8
    narration_seconds = audio_duration(narration)
    if narration_seconds + hook_duration > 58.6:
        raise RuntimeError(f"narration is too long for a one-minute Short: {narration_seconds:.2f}s")
    shifted = [{**item, "offset": round(float(item["offset"]) + hook_duration, 3)} for item in timings]
    captions = SubtitleWriter().from_timings(
        shifted, output / "captions.ass", list(script["important_terms"]),
        hook_text=str(script["hook"]), hook_duration=hook_duration,
    )
    final_duration = round(max(55.0, narration_seconds + hook_duration + 0.65), 3)
    hook_start = find_hook_start(source, source_duration, hook_duration)
    edit = compose_reddit_short(source, narration, captions, output / "short.mp4",
                                final_duration, hook_duration, hook_start)
    validation = validate_story_short(output / "short.mp4", 54.0, 60.0)
    write_json(output / "validation.json", {"valid": validation.valid,
                                               "errors": list(validation.errors), "probe": validation.probe})
    if not validation.valid:
        raise RuntimeError("final validation failed: " + "; ".join(validation.errors))

    source_info = {"video_id": post.post_id, "title": post.title, "source_url": post.post_url,
                   "channel": f"r/{post.subreddit}", "author": post.author,
                   "video_url": post.video_url, "subject": script["subject"],
                   "is_kpop": script["is_kpop"],
                   "authorization_basis": "Reddit-hosted video transformed with narration and attribution"}
    hook = {"text": script["hook"], "duration": hook_duration, "source_start": hook_start,
            "method": "scene-change cold open from original Reddit video"}
    job = {
        "job_id": seed, "title": str(script["title"])[:88],
        "description": (f"A Lululala recap of a {script['subject']} video shared by {post.author} "
                        f"in r/{post.subreddit}. Reddit reactions and unverified context are clearly attributed.\n\n"
                        f"Original Reddit post: {post.post_url}\n\n"
                        "#Lululala #celebrity #kpop #popculture #shorts"),
        "tags": ["Lululala", "celebrity", "K-pop", "pop culture", "Reddit", "shorts"],
        "privacy_status": "public", "thumbnail_file": "", "source_video_id": post.post_id,
    }
    selected = {"post_id": post.post_id, "subreddit": post.subreddit, "author": post.author,
                "title": post.title, "body": post.body, "comments_used": list(post.comments[:2]),
                "narration": script["narration"], "word_count": script["word_count"],
                "subject": script["subject"], "is_kpop": script["is_kpop"]}
    write_json(output / "source_info.json", source_info)
    write_json(output / "selected_story.json", selected)
    write_json(output / "hook.json", hook)
    write_json(output / "edit_plan.json", edit)
    write_json(output / "reference_media.json", {"source": "reddit", "post_url": post.post_url,
                                                   "stock_media_used": False})
    write_json(output / "job.json", job)
    write_json(output / "performance.json", {"final_duration": final_duration,
                                               "source_bytes": source.stat().st_size,
                                               "final_bytes": (output / "short.mp4").stat().st_size})
    (output / "optimization_report.md").write_text(
        "# Lululala celebrity edit\n\nOriginal Reddit-hosted video, cold-open hook, attributed fan-reaction narration, fixed-frame cuts, and pink emphasis captions.\n",
        encoding="utf-8",
    )
    report = {"source": source_info, "selected_story": selected, "hook": hook,
              "edit_plan": edit, "validation": {"valid": True, "errors": []},
              "output": str(output / "short.mp4")}
    write_json(output / "run_report.json", report)
    note(f"SUCCESS: {final_duration:.2f}s Lululala celebrity Short ready for YouTube")
    return report


def main() -> int:
    try:
        run()
        return 0
    except Exception as exc:
        print(f"PIPELINE ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
