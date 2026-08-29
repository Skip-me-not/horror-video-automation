from __future__ import annotations

import argparse
import os
import random
import shutil
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
from .downloader import download_audio, download_captions, download_selected_video, use_local_source
from .history import HistoryStore
from .hook_builder import build_hook
from .horror_scorer import HorrorScorer
from .performance import PerformanceTracker, disk_status, write_optimization_report
from .podcast_rss import (PodcastEpisode, download_episode_audio, download_episode_transcript,
                          make_audio_visual_source, search_podcast_episodes)
from .reference_query_builder import build_reference_queries
from .shot_planner import attach_stock_assets, build_edit_plan
from .silence_detector import detect_silences
from .stock_media import StockMediaClient
from .story_segment_builder import build_story_segment
from .utils import ffprobe, sha256_text, write_json
from .validator import validate_story_short
from .youtube_search import SourceResult, assert_authorized, filter_results, inspect_url, search


def _log(path: Path, message: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as output:
        output.write(f"[{stamp}] {message}\n")
    print(message)


def _duration(path: Path, info: dict[str, Any]) -> float:
    if info.get("duration"):
        return float(info["duration"])
    return float(ffprobe(path).get("format", {}).get("duration") or 0)


def _source_summary(info: dict[str, Any], authorization: str) -> dict[str, Any]:
    return {
        "video_id": str(info.get("id") or ""), "title": str(info.get("title") or "Untitled source"),
        "source_url": str(info.get("webpage_url") or info.get("original_url") or ""),
        "channel": str(info.get("channel") or info.get("uploader") or ""),
        "channel_id": str(info.get("channel_id") or info.get("uploader_id") or ""),
        "duration": float(info.get("duration") or 0), "license": str(info.get("license") or ""),
        "authorization_basis": authorization,
    }


def _known_timestamp(captions: list[Caption], start: float, source_duration: float,
                     settings: Settings, target: float) -> dict[str, Any]:
    source_length = min(165.0, max(settings.min_final_duration * settings.source_speed,
                                   target * settings.source_speed))
    end = min(source_duration, start + source_length)
    transcript = " ".join(item.text for item in captions if item.end > start and item.start < end)
    return {"start": start, "end": end, "source_duration": end - start,
            "final_duration": (end - start) / settings.source_speed, "transcript": transcript,
            "score": 999.0, "has_payoff_signal": True, "selection_mode": "known-timestamp"}


def _audio_only_story(audio: Path, duration: float, settings: Settings, target: float) -> dict[str, Any]:
    changes = energy_changes(audio)
    source_length = min(165.0, max(settings.min_final_duration * settings.source_speed,
                                   target * settings.source_speed))
    if not changes:
        start = max(0.0, min(duration - source_length, duration * 0.28))
        end = min(duration, start + source_length)
        return {"start": round(start, 3), "end": round(end, 3),
                "source_duration": round(end - start, 3),
                "final_duration": round((end - start) / settings.source_speed, 3),
                "anchor": {}, "transcript": "", "score": 0.0,
                "has_payoff_signal": False, "selection_mode": "audio-only-safe-fallback"}
    anchor = max(changes, key=lambda item: abs(item["delta_db"]))
    start = max(0.0, min(duration - source_length, float(anchor["time"]) - source_length * 0.48))
    end = min(duration, start + source_length)
    return {"start": round(start, 3), "end": round(end, 3),
            "source_duration": round(end - start, 3),
            "final_duration": round((end - start) / settings.source_speed, 3),
            "anchor": {"audio_energy_change": anchor}, "transcript": "",
            "score": abs(anchor["delta_db"]), "has_payoff_signal": False,
            "selection_mode": "audio-only"}


def _score_transcript(captions: list[Caption], triggers: dict[str, Any],
                      scoring: dict[str, Any]) -> list[dict[str, Any]]:
    moments = HorrorScorer(triggers, scoring).score_all(captions)
    return generate_candidates(captions, moments, float(scoring["minimum_anchor_score"]))[:10]


def _candidate_windows(candidates: list[dict[str, Any]], duration: float) -> list[tuple[float, float]]:
    return [(max(0.0, float(item["anchor"]["start"]) - 90.0),
             min(duration, float(item["anchor"]["end"]) + 90.0)) for item in candidates[:5]]


def _select_caption_story(captions: list[Caption], candidates: list[dict[str, Any]],
                          audio: Path, duration: float, settings: Settings, target: float,
                          scoring: dict[str, Any]) -> dict[str, Any]:
    windows = _candidate_windows(candidates, duration)
    silences = detect_silences(audio, ranges=windows)
    energy = energy_changes(audio, ranges=windows)
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        proposal = candidate.copy()
        anchor_time = float(candidate["anchor"]["start"])
        local_delta = max((abs(item["delta_db"]) for item in energy
                           if abs(float(item["time"]) - anchor_time) <= 30.0), default=0.0)
        proposal["audio_energy_bonus"] = round(min(3.0, local_delta / 5.0), 3)
        proposal["score"] = float(proposal["score"]) + proposal["audio_energy_bonus"]
        ranked.append(proposal)
    ranked.sort(key=lambda item: float(item["score"]), reverse=True)
    selected = build_story_segment(captions, ranked, silences, duration, settings.source_speed,
                                   settings.min_final_duration, target, settings.max_final_duration,
                                   list(scoring["ending_terms"]))
    selected["selection_mode"] = "transcript-first-local-audio"
    return selected


def _remote_attempt(result: SourceResult, attempt_dir: Path, args: argparse.Namespace,
                    settings: Settings, target: float, triggers: dict[str, Any],
                    scoring: dict[str, Any], history: HistoryStore, perf: PerformanceTracker,
                    log: Path) -> dict[str, Any]:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    if not args.force_reprocess and result.video_id in history.used_source_ids():
        raise RuntimeError("EARLY_SKIP_ALREADY_PROCESSED")
    try:
        with perf.stage("caption_retrieval"):
            caption_payload = download_captions(result.url, attempt_dir / "captions")
    except Exception as exc:
        _log(log, f"CAPTION_RETRIEVAL_FAILED_AUDIO_FALLBACK: {str(exc)[:400]}")
        caption_payload = {"info": {"id": result.video_id, "title": result.title,
                                     "webpage_url": result.url, "channel": result.channel,
                                     "channel_id": result.channel_id, "duration": result.duration,
                                     "license": result.license}, "subtitles": None}
    info = caption_payload["info"]
    duration = float(info.get("duration") or result.duration)
    captions = parse_vtt(Path(caption_payload["subtitles"])) if caption_payload.get("subtitles") else []
    _log(log, f"Caption-first: {len(captions)} cues for {result.video_id}")

    candidates: list[dict[str, Any]] = []
    if captions and args.start is None:
        with perf.stage("transcript_scoring"):
            candidates = _score_transcript(captions, triggers, scoring)
        if not candidates:
            raise RuntimeError("EARLY_SKIP_INSUFFICIENT_HORROR_SIGNALS")
        _log(log, f"Transcript-first candidates: {len(candidates)}")

    if args.start is not None:
        selected = _known_timestamp(captions, args.start, duration, settings, target)
        audio = None
    else:
        disk_status(attempt_dir, settings.disk_warning_free_gb, settings.disk_abort_free_gb,
                    before_download=True)
        with perf.stage("audio_download"):
            audio = download_audio(result.url, attempt_dir / "audio")
        perf.set(audio_only_analysis=True, audio_bytes=audio.stat().st_size)
        with perf.stage("moment_detection"):
            selected = (_select_caption_story(captions, candidates, audio, duration, settings, target, scoring)
                        if captions else _audio_only_story(audio, duration, settings, target))
        audio.unlink(missing_ok=True)

    transcript_hash = sha256_text(str(selected.get("transcript") or
                                      f"audio:{selected['start']:.3f}:{selected['end']:.3f}"))
    if (not args.force_reprocess and history.contains_story(result.video_id, transcript_hash,
                                                            float(selected["start"]), float(selected["end"]))):
        raise RuntimeError("EARLY_SKIP_DUPLICATE_STORY")
    selected["transcript_hash"] = transcript_hash

    disk_status(attempt_dir, settings.disk_warning_free_gb, settings.disk_abort_free_gb,
                before_download=True)
    with perf.stage("selected_range_download"):
        media = download_selected_video(result.url, attempt_dir / "source", float(selected["start"]),
                                        float(selected["end"]), settings)
    if not media["range_downloaded"]:
        _log(log, f"RANGE_DOWNLOAD_FAILED_FALLBACK_FULL: {media['range_error'][:400]}")
    perf.set(range_video_download=bool(media["range_downloaded"]),
             full_video_downloaded=not bool(media["range_downloaded"]),
             source_video_bytes=Path(media["video"]).stat().st_size,
             source_download_bytes=Path(media["video"]).stat().st_size,
             full_source_duration_seconds=duration,
             selected_range_duration_seconds=round(float(selected["end"]) - float(selected["start"]), 3))
    _log(log, f"Source download complete: range={media['range_downloaded']} bytes={Path(media['video']).stat().st_size}")
    return {"source": Path(media["video"]), "media_start": float(media["media_start"]),
            "captions": captions, "selected": selected, "info": info,
            "authorization_basis": "automated keyword search; license not enforced"}


def _podcast_attempt(episode: PodcastEpisode, attempt_dir: Path, args: argparse.Namespace,
                     settings: Settings, target: float, triggers: dict[str, Any],
                     scoring: dict[str, Any], history: HistoryStore, perf: PerformanceTracker,
                     log: Path) -> dict[str, Any]:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    if not args.force_reprocess and episode.episode_id in history.used_source_ids():
        raise RuntimeError("EARLY_SKIP_ALREADY_PROCESSED_RSS_EPISODE")
    transcript_path = None
    try:
        with perf.stage("podcast_transcript_retrieval"):
            transcript_path = download_episode_transcript(episode, attempt_dir / "episode.vtt")
    except Exception as exc:
        _log(log, f"RSS_TRANSCRIPT_UNAVAILABLE_AUDIO_FALLBACK: {str(exc)[:300]}")
    captions = parse_vtt(transcript_path) if transcript_path else []
    disk_status(attempt_dir, settings.disk_warning_free_gb, settings.disk_abort_free_gb,
                before_download=True)
    with perf.stage("podcast_audio_download"):
        audio = download_episode_audio(episode, attempt_dir / "episode_audio.mp3")
    duration = episode.duration or _duration(audio, {})
    if not settings.min_source_duration <= duration <= settings.max_source_duration:
        raise RuntimeError(f"RSS episode duration outside limits: {duration:.1f}s")
    perf.set(audio_only_analysis=True, audio_bytes=audio.stat().st_size)
    if captions and args.start is None:
        candidates = _score_transcript(captions, triggers, scoring)
        if not candidates:
            raise RuntimeError("EARLY_SKIP_INSUFFICIENT_RSS_HORROR_SIGNALS")
        with perf.stage("moment_detection"):
            selected = _select_caption_story(captions, candidates, audio, duration, settings, target, scoring)
    elif args.start is not None:
        selected = _known_timestamp(captions, args.start, duration, settings, target)
    else:
        with perf.stage("moment_detection"):
            selected = _audio_only_story(audio, duration, settings, target)
        selected["transcript"] = episode.description or episode.title
    transcript_hash = sha256_text(str(selected.get("transcript") or
                                      f"audio:{selected['start']:.3f}:{selected['end']:.3f}"))
    if (not args.force_reprocess and history.contains_story(episode.episode_id, transcript_hash,
                                                            float(selected["start"]), float(selected["end"]))):
        raise RuntimeError("EARLY_SKIP_DUPLICATE_RSS_STORY")
    selected["transcript_hash"] = transcript_hash
    with perf.stage("podcast_visual_source"):
        source = make_audio_visual_source(audio, attempt_dir / "rss_source.mp4",
                                          float(selected["start"]), float(selected["end"]))
    audio.unlink(missing_ok=True)
    perf.set(range_video_download=False, full_video_downloaded=False,
             source_video_bytes=source.stat().st_size, source_download_bytes=source.stat().st_size,
             full_source_duration_seconds=duration,
             selected_range_duration_seconds=round(float(selected["end"]) - float(selected["start"]), 3))
    info = {"id": episode.episode_id, "title": episode.title,
            "webpage_url": episode.webpage_url, "channel": episode.podcast,
            "channel_id": "podcast-rss", "duration": duration, "license": ""}
    _log(log, f"Podcast RSS fallback ready: {episode.podcast} — {episode.title}")
    return {"source": source, "media_start": float(selected["start"]), "captions": captions,
            "selected": selected, "info": info,
            "authorization_basis": "public podcast RSS fallback; license not enforced"}


def _local_attempt(path: Path, args: argparse.Namespace, settings: Settings, target: float,
                   triggers: dict[str, Any], scoring: dict[str, Any], history: HistoryStore,
                   perf: PerformanceTracker, log: Path) -> dict[str, Any]:
    payload = use_local_source(path, settings.root / "downloads")
    source, info = Path(payload["video"]), payload["info"]
    duration = _duration(source, info)
    info["duration"] = duration
    captions = parse_vtt(Path(payload["subtitles"])) if payload.get("subtitles") else []
    _log(log, f"Local source with {len(captions)} caption cues")
    if args.start is not None:
        selected = _known_timestamp(captions, args.start, duration, settings, target)
    elif captions:
        candidates = _score_transcript(captions, triggers, scoring)
        if not candidates:
            raise RuntimeError("EARLY_SKIP_INSUFFICIENT_HORROR_SIGNALS")
        with perf.stage("moment_detection"):
            selected = _select_caption_story(captions, candidates, source, duration, settings, target, scoring)
    else:
        with perf.stage("moment_detection"):
            selected = _audio_only_story(source, duration, settings, target)
    source_id = str(info.get("id") or source.stem)
    transcript_hash = sha256_text(str(selected.get("transcript") or
                                      f"audio:{selected['start']:.3f}:{selected['end']:.3f}"))
    if (not args.force_reprocess and history.contains_story(source_id, transcript_hash,
                                                            float(selected["start"]), float(selected["end"]))):
        raise RuntimeError("EARLY_SKIP_DUPLICATE_STORY")
    selected["transcript_hash"] = transcript_hash
    perf.set(full_source_duration_seconds=duration,
             selected_range_duration_seconds=round(float(selected["end"]) - float(selected["start"]), 3),
             source_video_bytes=source.stat().st_size, source_download_bytes=0)
    return {"source": source, "media_start": 0.0, "captions": captions, "selected": selected,
            "info": info, "authorization_basis": "user-supplied local file"}


def _choose_and_prepare(args: argparse.Namespace, settings: Settings, target: float,
                        triggers: dict[str, Any], scoring: dict[str, Any], history: HistoryStore,
                        run_dir: Path, perf: PerformanceTracker, log: Path) -> dict[str, Any]:
    if args.video_url and Path(args.video_url).is_file():
        return _local_attempt(Path(args.video_url), args, settings, target, triggers, scoring, history, perf, log)

    if args.video_url:
        with perf.stage("search_metadata"):
            info = inspect_url(args.video_url)
        assert_authorized(info, settings, args.authorized)
        entries = filter_results([info], replace(settings, min_source_duration=0),
                                 set() if args.force_reprocess else history.used_source_ids())
        if not entries:
            raise RuntimeError("manual URL failed duration/live/history metadata checks")
        return _remote_attempt(entries[0], run_dir / "source-1", args, settings, target,
                               triggers, scoring, history, perf, log)

    search_config = read_json(settings.root / "config" / "search_keywords.json")
    keyword = args.keyword or random.choice(search_config["keywords"])
    with perf.stage("search_metadata"):
        results = search(keyword, int(search_config.get("videos_per_keyword", 20)), settings,
                         set() if args.force_reprocess else history.used_source_ids())
    random.shuffle(results)
    errors: list[str] = []
    if not results:
        errors.append("youtube-search: no unused source passed metadata filters")
    for index, result in enumerate(results[:settings.max_sources_per_run], start=1):
        _log(log, f"Trying metadata-approved source {index}/{settings.max_sources_per_run}: {result.title}")
        try:
            return _remote_attempt(result, run_dir / f"source-{index}", args, settings, target,
                                   triggers, scoring, history, perf, log)
        except Exception as exc:
            errors.append(f"{result.video_id}: {exc}")
            _log(log, f"Source skipped before final render: {exc}")
            attempt_dir = run_dir / f"source-{index}"
            if attempt_dir.is_dir() and run_dir.resolve() in attempt_dir.resolve().parents:
                shutil.rmtree(attempt_dir)
    _log(log, "YouTube sources unavailable; switching to no-login public podcast RSS fallback")
    with perf.stage("podcast_rss_search"):
        episodes = search_podcast_episodes(keyword, settings,
                                           set() if args.force_reprocess else history.used_source_ids())
    for index, episode in enumerate(episodes[:settings.max_sources_per_run], start=1):
        _log(log, f"Trying RSS podcast {index}/{settings.max_sources_per_run}: {episode.title}")
        try:
            return _podcast_attempt(episode, run_dir / f"rss-source-{index}", args, settings, target,
                                    triggers, scoring, history, perf, log)
        except Exception as exc:
            errors.append(f"{episode.episode_id}: {exc}")
            _log(log, f"RSS source skipped before final render: {exc}")
            attempt_dir = run_dir / f"rss-source-{index}"
            if attempt_dir.is_dir() and run_dir.resolve() in attempt_dir.resolve().parents:
                shutil.rmtree(attempt_dir)
    raise RuntimeError("all YouTube and podcast RSS source attempts failed: " + " | ".join(errors))


def _print_performance(payload: dict[str, Any]) -> None:
    print("\n=== PIPELINE PERFORMANCE ===")
    for name, seconds in payload["stages_seconds"].items():
        print(f"{name:28} {seconds:8.2f} sec")
    print(f"{'TOTAL':28} {payload['total_seconds']:8.2f} sec")
    for key in ("full_source_duration_seconds", "selected_range_duration_seconds",
                "full_video_downloaded", "audio_only_analysis", "range_video_download",
                "source_video_bytes", "stock_bytes", "bytes_downloaded_total", "final_file_bytes",
                "ffmpeg_full_encodes",
                "ffmpeg_cache_hit", "yt_dlp_cache_hit", "pip_cache_hit"):
        if key in payload:
            print(f"{key:28} {payload[key]}")


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root)
    if args.source_speed is not None:
        settings = replace(settings, source_speed=args.source_speed)
    if args.debug_artifacts:
        settings = replace(settings, debug_artifacts=True)
    target = args.target_duration or settings.target_final_duration
    if not settings.min_final_duration <= target <= settings.max_final_duration:
        raise ValueError("target duration must be within configured min/max limits")

    output = root / "output"
    runner_temp = Path(os.getenv("RUNNER_TEMP") or root / "temp")
    run_dir = runner_temp / "horror-short" / (os.getenv("GITHUB_RUN_ID") or f"local-{os.getpid()}")
    output.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    log = output / "processing.log"
    log.write_text("", encoding="utf-8")
    write_optimization_report(output / "optimization_report.md")
    perf = PerformanceTracker()
    perf.set(initial_disk=disk_status(run_dir, settings.disk_warning_free_gb,
                                      settings.disk_abort_free_gb, before_download=False))
    history = HistoryStore(root / "data" / "history.json", limit=300)
    triggers = read_json(root / "config" / "horror_triggers.json")
    scoring = read_json(root / "config" / "scoring.json")

    prepared = _choose_and_prepare(args, settings, target, triggers, scoring, history, run_dir, perf, log)
    source, selected = Path(prepared["source"]), prepared["selected"]
    captions: list[Caption] = prepared["captions"]
    source_info = _source_summary(prepared["info"], prepared["authorization_basis"])
    write_json(output / "source_info.json", source_info)
    write_json(output / "selected_story.json", selected)

    relative_captions = slice_captions(captions, float(selected["start"]),
                                       float(selected["end"]), settings.source_speed)
    anchor_matches = list((selected.get("anchor") or {}).get("matches") or [])
    hook = build_hook(str(selected.get("transcript") or ""), anchor_matches,
                      settings.hook_min_seconds, settings.hook_max_seconds)
    write_json(output / "hook.json", hook)
    final_duration = min(settings.hard_max_duration, float(selected["final_duration"]))

    mappings = read_json(root / "config" / "reference_keywords.json")
    query_events = build_reference_queries(relative_captions, mappings) if relative_captions else []
    if not query_events and prepared["authorization_basis"].startswith("public podcast RSS"):
        fallback_queries = ["dark hallway", "foggy woods", "security camera dark room",
                            "empty hospital", "human shadow hallway"]
        spacing = max(10.0, (final_duration - hook["duration"] - 10.0) / len(fallback_queries))
        query_events = [{"time": round(float(hook["duration"]) + 8.0 + index * spacing, 3),
                         "keyword": "rss-horror", "query": query, "transcript": episode_text}
                        for index, (query, episode_text) in enumerate(
                            zip(fallback_queries, [str(selected.get("transcript") or "podcast horror")]
                                * len(fallback_queries)))]
    with perf.stage("edit_planning"):
        draft_plan = build_edit_plan(final_duration, settings.source_speed, settings.horizontal_flip,
                                     hook, query_events, {}, settings.target_broll_ratio,
                                     settings.broll_min_seconds, settings.broll_max_seconds,
                                     settings.max_static_speaker_seconds, settings.target_broll_count,
                                     settings.max_broll_count)
        write_json(output / "edit_plan.json", draft_plan)

    assets: dict[str, dict[str, Any]] = {}
    if not args.no_stock:
        stock_dir = run_dir / "stock"
        client = StockMediaClient(stock_dir, settings.enable_pexels, settings.enable_pixabay)
        slots = [item for item in draft_plan["segments"] if item["type"] == "planned_broll"]
        with perf.stage("stock_lookup_download"):
            for slot in slots:
                query = str(slot["query"])
                if query in assets:
                    continue
                try:
                    asset = client.acquire(query, prefer_video=slot["preferred_media_type"] == "video")
                except Exception as exc:
                    _log(log, f"Stock fallback for {query!r}: {exc}")
                    asset = None
                if asset:
                    assets[query] = asset.as_dict()
    plan = attach_stock_assets(draft_plan, assets)
    plan["source_media_start"] = prepared["media_start"]
    write_json(output / "edit_plan.json", plan)
    write_json(output / "reference_media.json", {"queries": query_events, "assets": list(assets.values())})

    trigger_words = {phrase.casefold() for phrases in triggers.values() for phrase in phrases}
    ass = write_ass(output / "captions.ass", relative_captions, hook, trigger_words,
                    settings.output_width, settings.output_height)
    before_render_disk = disk_status(run_dir, settings.disk_warning_free_gb,
                                     settings.disk_abort_free_gb, before_download=False)
    _log(log, f"Disk before render: {before_render_disk['free_gb']:.2f} GB free")
    source_trim_start = max(0.0, float(selected["start"]) - float(prepared["media_start"]))
    with perf.stage("final_render"):
        final = compose(source, plan, ass, output / "short.mp4", run_dir / "render", settings,
                        source_trim_start=source_trim_start,
                        source_duration=float(selected["end"]) - float(selected["start"]))
    perf.set(ffmpeg_full_encodes=1)
    with perf.stage("validation"):
        validation = validate_story_short(final, settings.min_final_duration, settings.hard_max_duration)
    write_json(output / "validation.json", {"valid": validation.valid,
                                             "errors": list(validation.errors), "probe": validation.probe})
    if not validation.valid:
        raise RuntimeError("final validation failed: " + "; ".join(validation.errors))

    source_id = source_info["video_id"] or source.stem
    history.append({"source_video_id": source_id, "source_start": selected["start"],
                    "source_end": selected["end"], "transcript_hash": selected["transcript_hash"],
                    "hook_template": hook["text"],
                    "reference_queries": [event["query"] for event in query_events],
                    "generated_timestamp": datetime.now(timezone.utc).isoformat()})
    stock_bytes = sum(Path(item["local_path"]).stat().st_size for item in assets.values())
    downloaded_total = (int(perf.metrics.get("audio_bytes", 0))
                        + int(perf.metrics.get("source_download_bytes", 0)) + stock_bytes)
    perf.set(stock_asset_count=len(assets), stock_bytes=stock_bytes,
             bytes_downloaded_total=downloaded_total, final_file_bytes=final.stat().st_size,
             final_disk=disk_status(run_dir, settings.disk_warning_free_gb,
                                    settings.disk_abort_free_gb, before_download=False))
    performance = perf.write(output / "performance.json")
    _print_performance(performance)
    report = {"source": source_info, "selected_story": selected, "hook": hook,
              "edit_plan": plan, "validation": {"valid": True, "errors": []},
              "performance": performance, "output": str(final)}
    write_json(output / "run_report.json", report)
    _log(log, f"SUCCESS: coherent {final_duration:.2f}s podcast horror segment validated at {final}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Find a scary podcast segment, then edit one vertical Short")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--video-url", help="Authorized URL or local media path")
    source.add_argument("--keyword", help="Search videos using this horror-podcast keyword")
    parser.add_argument("--source-speed", type=float)
    parser.add_argument("--target-duration", type=float)
    parser.add_argument("--start", type=float, help="Known source timestamp for manual debug")
    parser.add_argument("--no-stock", action="store_true")
    parser.add_argument("--force-reprocess", action="store_true")
    parser.add_argument("--authorized", action="store_true",
                        help="Confirm that you own or have permission to download and reuse this source")
    parser.add_argument("--debug-artifacts", action="store_true")
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
