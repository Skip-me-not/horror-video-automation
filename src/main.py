from __future__ import annotations

import argparse
import random
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audio_analysis import energy_changes
from .candidate_generator import generate_candidates
from .caption_renderer import write_ass
from .captions import Caption, parse_vtt, slice_captions
from .compositor import compose
from .config_loader import Settings, load_settings, read_json
from .downloader import download_source, use_local_source
from .history import HistoryStore
from .hook_builder import build_hook
from .horror_scorer import HorrorScorer
from .reference_query_builder import build_reference_queries
from .shot_planner import build_edit_plan
from .silence_detector import detect_silences
from .stock_media import StockMediaClient
from .story_segment_builder import build_story_segment
from .utils import ffprobe, sha256_text, write_json
from .validator import validate_story_short
from .video_transform import transform_source
from .youtube_search import assert_authorized, inspect_url, search


def _log(path: Path, message: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as output:
        output.write(f"[{stamp}] {message}\n")
    print(message)


def _duration(path: Path, info: dict[str, Any]) -> float:
    if info.get("duration"):
        return float(info["duration"])
    payload = ffprobe(path)
    return float(payload.get("format", {}).get("duration") or 0)


def _source_summary(info: dict[str, Any], authorization: str) -> dict[str, Any]:
    return {
        "video_id": str(info.get("id") or ""),
        "title": str(info.get("title") or "Untitled source"),
        "source_url": str(info.get("webpage_url") or info.get("original_url") or ""),
        "channel": str(info.get("channel") or info.get("uploader") or ""),
        "channel_id": str(info.get("channel_id") or info.get("uploader_id") or ""),
        "duration": float(info.get("duration") or 0),
        "authorization_basis": authorization,
    }


def _select_source(args: argparse.Namespace, settings: Settings, history: HistoryStore,
                   log: Path) -> dict[str, Any]:
    downloads = settings.root / "downloads"
    if args.video_url:
        local = Path(args.video_url)
        if local.is_file():
            _log(log, f"Using explicitly supplied local source: {local}")
            payload = use_local_source(local, downloads)
            payload["authorization_basis"] = "user-supplied local file"
            return payload
        info = inspect_url(args.video_url)
        assert_authorized(info, settings, args.authorized)
        _log(log, f"Downloading authorized source video {info.get('id')}")
        payload = download_source(args.video_url, downloads, settings)
        payload["authorization_basis"] = ("explicit --authorized confirmation" if args.authorized
                                            else "authorization check disabled in settings")
        return payload

    search_config = read_json(settings.root / "config" / "search_keywords.json")
    keyword = args.keyword or random.choice(search_config["keywords"])
    _log(log, f"Searching metadata first: {keyword}")
    results = search(keyword, int(search_config.get("videos_per_keyword", 2)), settings,
                     set() if args.force_reprocess else history.used_source_ids())
    if not results:
        raise RuntimeError("no unused Creative Commons/reuse-allowed source passed duration/live filters")
    chosen = random.choice(results)
    _log(log, f"Randomly selected reusable source {chosen.video_id}: {chosen.title}")
    payload = download_source(chosen.url, downloads, settings)
    payload["authorization_basis"] = f"search metadata license: {chosen.license}"
    return payload


def _audio_only_story(source: Path, duration: float, settings: Settings,
                      target: float) -> dict[str, Any]:
    changes = energy_changes(source)
    if not changes:
        raise RuntimeError("captions unavailable and audio confidence too low")
    anchor = max(changes, key=lambda item: abs(item["delta_db"]))
    source_length = min(165.0, max(settings.min_final_duration * settings.source_speed,
                                   target * settings.source_speed))
    start = max(0.0, min(duration - source_length, float(anchor["time"]) - source_length * 0.48))
    end = min(duration, start + source_length)
    return {"start": round(start, 3), "end": round(end, 3),
            "source_duration": round(end - start, 3),
            "final_duration": round((end - start) / settings.source_speed, 3),
            "anchor": {"audio_energy_change": anchor}, "transcript": "", "score": abs(anchor["delta_db"]),
            "has_payoff_signal": False, "selection_mode": "audio-only"}


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root)
    if args.source_speed is not None:
        settings = replace(settings, source_speed=args.source_speed)
    target_duration = args.target_duration or settings.target_final_duration
    if not settings.min_final_duration <= target_duration <= settings.max_final_duration:
        raise ValueError("target duration must be within configured min/max limits")

    output = root / "output"
    temp = root / "temp"
    output.mkdir(parents=True, exist_ok=True)
    temp.mkdir(parents=True, exist_ok=True)
    processing_log = output / "processing.log"
    processing_log.write_text("", encoding="utf-8")
    history = HistoryStore(root / "data" / "history.json", limit=300)
    source_payload = _select_source(args, settings, history, processing_log)
    source = Path(source_payload["video"])
    info = source_payload["info"]
    source_duration = _duration(source, info)
    info["duration"] = source_duration
    if not settings.min_source_duration <= source_duration <= settings.max_source_duration:
        raise RuntimeError("source duration is outside the configured 10-180 minute range")
    source_info = _source_summary(info, source_payload["authorization_basis"])
    write_json(output / "source_info.json", source_info)

    captions: list[Caption] = []
    subtitle_path = source_payload.get("subtitles")
    if subtitle_path:
        captions = parse_vtt(Path(subtitle_path))
    _log(processing_log, f"Loaded {len(captions)} caption entries")

    triggers = read_json(root / "config" / "horror_triggers.json")
    scoring = read_json(root / "config" / "scoring.json")
    if args.start is not None:
        source_length = min(165.0, max(settings.min_final_duration * settings.source_speed,
                                       target_duration * settings.source_speed))
        start, end = args.start, min(source_duration, args.start + source_length)
        transcript = " ".join(item.text for item in captions if item.end > start and item.start < end)
        selected = {"start": start, "end": end, "source_duration": end - start,
                    "final_duration": (end - start) / settings.source_speed, "transcript": transcript,
                    "score": 999.0, "has_payoff_signal": True, "selection_mode": "known-timestamp"}
    elif captions:
        moments = HorrorScorer(triggers, scoring).score_all(captions)
        candidates = generate_candidates(captions, moments, float(scoring["minimum_anchor_score"]))
        _log(processing_log, f"Generated {len(candidates)} deterministic horror candidates")
        silences = detect_silences(source)
        selected = build_story_segment(captions, candidates, silences, source_duration,
                                       settings.source_speed, settings.min_final_duration,
                                       target_duration, settings.max_final_duration,
                                       list(scoring["ending_terms"]))
        selected["selection_mode"] = "transcript-rules"
    else:
        selected = _audio_only_story(source, source_duration, settings, target_duration)

    transcript_hash = sha256_text(str(selected.get("transcript") or
                                      f"audio:{selected['start']:.3f}:{selected['end']:.3f}"))
    source_id = source_info["video_id"] or source.stem
    if (not args.force_reprocess and history.contains_story(source_id, transcript_hash,
                                                            float(selected["start"]), float(selected["end"]))):
        raise RuntimeError("the same or overlapping story segment already exists in history")
    selected["transcript_hash"] = transcript_hash
    write_json(output / "selected_story.json", selected)

    relative_captions = slice_captions(captions, float(selected["start"]),
                                       float(selected["end"]), settings.source_speed)
    anchor_matches = list((selected.get("anchor") or {}).get("matches") or [])
    hook = build_hook(str(selected.get("transcript") or ""), anchor_matches,
                      settings.hook_min_seconds, settings.hook_max_seconds)
    write_json(output / "hook.json", hook)

    normalized = temp / "source-vertical.mp4"
    transform_source(source, normalized, float(selected["start"]), float(selected["end"]), settings)
    final_duration = min(settings.hard_max_duration, float(selected["final_duration"]))

    mappings = read_json(root / "config" / "reference_keywords.json")
    query_events = build_reference_queries(relative_captions, mappings) if relative_captions else []
    assets: dict[str, dict[str, Any]] = {}
    if not args.no_stock and query_events:
        client = StockMediaClient(root / "stock", settings.enable_pexels, settings.enable_pixabay)
        for index, event in enumerate(query_events[:12]):
            try:
                asset = client.acquire(event["query"], prefer_video=index % 2 == 0)
            except Exception as exc:
                _log(processing_log, f"Stock fallback for {event['query']!r}: {exc}")
                asset = None
            if asset:
                assets[event["query"]] = asset.as_dict()
    write_json(output / "reference_media.json", {"queries": query_events, "assets": list(assets.values())})

    plan = build_edit_plan(final_duration, settings.source_speed, settings.horizontal_flip, hook,
                           query_events, assets, settings.target_broll_ratio,
                           settings.broll_min_seconds, settings.broll_max_seconds,
                           settings.max_static_speaker_seconds)
    write_json(output / "edit_plan.json", plan)

    trigger_words = {phrase.casefold() for phrases in triggers.values() for phrase in phrases}
    ass = write_ass(output / "captions.ass", relative_captions, hook, trigger_words,
                    settings.output_width, settings.output_height)
    final = compose(normalized, plan, ass, output / "short.mp4", temp, settings)
    validation = validate_story_short(final, settings.min_final_duration,
                                      settings.hard_max_duration)
    write_json(output / "validation.json", {"valid": validation.valid,
                                             "errors": list(validation.errors), "probe": validation.probe})
    if not validation.valid:
        raise RuntimeError("final validation failed: " + "; ".join(validation.errors))

    history.append({"source_video_id": source_id, "source_start": selected["start"],
                    "source_end": selected["end"], "transcript_hash": transcript_hash,
                    "hook_template": hook["text"],
                    "reference_queries": [event["query"] for event in query_events],
                    "generated_timestamp": datetime.now(timezone.utc).isoformat()})
    report = {"source": source_info, "selected_story": selected, "hook": hook,
              "edit_plan": plan, "validation": {"valid": True, "errors": []},
              "output": str(final)}
    write_json(output / "run_report.json", report)
    _log(processing_log, f"SUCCESS: {final_duration:.2f}s story Short validated at {final}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a deterministic edited horror story Short")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--video-url", help="Authorized URL or local media path")
    source.add_argument("--keyword", help="Search configured authorized channels with this keyword")
    parser.add_argument("--source-speed", type=float)
    parser.add_argument("--target-duration", type=float)
    parser.add_argument("--start", type=float, help="Known authorized source timestamp for Phase-1 testing")
    parser.add_argument("--no-stock", action="store_true")
    parser.add_argument("--force-reprocess", action="store_true")
    parser.add_argument("--authorized", action="store_true",
                        help="Confirm that you own or have permission to download and reuse this source")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    try:
        run_pipeline(args)
        return 0
    except Exception as exc:
        print(f"PIPELINE ERROR: {exc}", file=sys.stderr)
        if args.debug:
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
