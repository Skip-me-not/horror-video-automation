#!/usr/bin/env python3
"""Small, deterministic source and final-output quality gates for Reddit Shorts."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "content_quality.json"
REPORT_DIR = ROOT / "quality_reports"


class QualityError(RuntimeError):
    """A probe or quality configuration could not be used safely."""


def load_quality_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualityError(f"Unable to read content quality configuration: {exc}") from exc
    required = {
        "MIN_WIDTH", "MIN_HEIGHT", "MIN_FPS", "MIN_DURATION", "MAX_DURATION",
        "MIN_SOURCE_SCORE", "MIN_FINAL_SCORE", "RECENT_HISTORY_SIZE",
        "MIN_SOURCE_COUNT", "MAX_SOURCE_COUNT", "MAX_CANDIDATES_TO_DOWNLOAD",
        "HOOK_CLIP_MAX", "EARLY_CLIP_MAX", "NORMAL_CLIP_MAX", "ABSOLUTE_CLIP_MAX",
        "MAX_SINGLE_SOURCE_PERCENT", "DUPLICATE_HASH_DISTANCE", "MAX_SILENCE_SECONDS",
        "MAX_BLACK_SECONDS", "MIN_AUDIO_MEAN_DB", "MAX_AUDIO_PEAK_DB", "SOURCE_WEIGHTS",
        "TIER_A_SCORE", "TIER_B_SCORE", "TARGET_PUBLISHED_VIDEOS_PER_DAY",
        "INITIAL_CANDIDATES", "MAX_CANDIDATES", "MAX_CANDIDATES_TO_RENDER",
        "SELECTION_BONUS_DIFFERENT_TOPIC", "SELECTION_PENALTY_SAME_TOPIC",
        "SELECTION_PENALTY_SHARED_SOURCE",
        "SELECTION_PENALTY_REPEATED_CREATOR",
    }
    if not isinstance(config, dict) or required - config.keys():
        raise QualityError("Content quality configuration has missing fields")
    if not 1 <= config["MIN_SOURCE_COUNT"] <= config["MAX_SOURCE_COUNT"] <= 8:
        raise QualityError("Invalid source-count limits")
    if not 0 <= config["MIN_SOURCE_SCORE"] <= 100 or not 0 <= config["MIN_FINAL_SCORE"] <= 100:
        raise QualityError("Quality thresholds must be between 0 and 100")
    if not 65 <= config["MIN_FINAL_SCORE"] <= config["TIER_B_SCORE"] <= config["TIER_A_SCORE"] <= 100:
        raise QualityError("Quality tiers must preserve the absolute 65-point floor")
    if not 1 <= config["TARGET_PUBLISHED_VIDEOS_PER_DAY"] <= config["INITIAL_CANDIDATES"] <= config["MAX_CANDIDATES"] <= 16:
        raise QualityError("Invalid daily candidate-pool limits")
    if not 1 <= config["MAX_CANDIDATES_TO_RENDER"] <= config["MAX_CANDIDATES"]:
        raise QualityError("Invalid render budget")
    if not 0 < config["MAX_SINGLE_SOURCE_PERCENT"] <= 100:
        raise QualityError("Invalid source dominance limit")
    if sum(config["SOURCE_WEIGHTS"].values()) <= 0:
        raise QualityError("Source weights must be positive")
    return config


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fps(value: Any) -> float:
    try:
        numerator, denominator = str(value).split("/", 1)
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return _number(value)


def probe_media(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        text=True, capture_output=True,
    )
    if result.returncode != 0:
        raise QualityError(f"ffprobe failed for {path.name}: {result.stderr[-300:]}")
    try:
        payload = json.loads(result.stdout)
        video = next(stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video")
    except (ValueError, StopIteration) as exc:
        raise QualityError(f"No readable video stream in {path.name}") from exc
    fmt = payload.get("format") or {}
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    return {
        "duration": _number(video.get("duration") or fmt.get("duration")),
        "width": width,
        "height": height,
        "fps": _fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "bitrate": int(_number(video.get("bit_rate") or fmt.get("bit_rate"))),
        "file_size": path.stat().st_size,
        "aspect_ratio": round(width / height, 4) if height else 0,
        "has_audio": any(stream.get("codec_type") == "audio" for stream in payload.get("streams", [])),
    }


def _frame(path: Path, second: float) -> bytes:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{second:.3f}",
         "-i", str(path), "-frames:v", "1", "-vf", "scale=9:8,format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True,
    )
    return result.stdout if result.returncode == 0 and len(result.stdout) == 72 else b""


def _dhash(pixels: bytes) -> str:
    bits = 0
    for row in range(8):
        for column in range(8):
            bits = (bits << 1) | (pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return f"{bits:016x}"


def sample_hashes(path: Path, duration: float) -> tuple[list[str], float, float]:
    samples: list[str] = []
    first_luma = 0.0
    for index, fraction in enumerate((0.02, 0.25, 0.50, 0.75)):
        pixels = _frame(path, min(max(0, duration - 0.2), duration * fraction))
        if pixels:
            samples.append(_dhash(pixels))
            if index == 0:
                first_luma = sum(pixels) / len(pixels)
    opening_pixels = _frame(path, min(max(0, duration - 0.2), 1.2))
    opening_motion = (
        (int(samples[0], 16) ^ int(_dhash(opening_pixels), 16)).bit_count() / 64
        if samples and opening_pixels else 0.0
    )
    return samples, first_luma, opening_motion


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def near_duplicate(left: list[str], right: list[str], max_distance: int) -> bool:
    if len(left) < 2 or len(right) < 2:
        return False
    matches = sum(
        min((int(value, 16) ^ int(other, 16)).bit_count() for other in right) <= max_distance
        for value in left
    )
    return matches >= 2


def inspect_source(
    path: Path, post: dict[str, Any], history: list[dict[str, Any]], config: dict[str, Any],
    *, now: float | None = None,
) -> dict[str, Any]:
    media = probe_media(path)
    source_url = "https://www.reddit.com" + post["permalink"]
    record: dict[str, Any] = {
        **media,
        "source_id": str(post["id"]), "source_url": source_url,
        "creator": str(post.get("author") or "unknown"),
        "media_url": str(post["video_url"]),
        "published_utc": _number(post.get("created_utc")) or None,
        "views": post.get("views"), "upvotes": post.get("score") if post.get("score_available", True) else None,
        "comments": post.get("num_comments"),
        "path": str(path), "score": 0, "reasons": [], "accepted": False,
    }
    hard: list[str] = []
    for key, minimum in (("width", "MIN_WIDTH"), ("height", "MIN_HEIGHT"), ("fps", "MIN_FPS"),
                         ("duration", "MIN_DURATION")):
        if media[key] < config[minimum]:
            hard.append(f"{key} {media[key]:g} below {config[minimum]}")
    if media["duration"] > config["MAX_DURATION"]:
        hard.append("source too long")
    if media["file_size"] < 10_000:
        hard.append("source file is too small")
    if hard:
        record["reasons"] = hard
        return record
    hashes, luma, motion = sample_hashes(path, media["duration"])
    record.update({"sha256": file_sha256(path), "frame_hashes": hashes,
                   "opening_luma": round(luma, 2), "opening_motion": round(motion, 3)})
    record["hook_suitable"] = luma >= 16 and motion >= 0.03
    if len(hashes) < 2:
        record["reasons"] = ["not enough decodable frames"]
        return record
    for old in history:
        if old.get("source_id") == record["source_id"] or old.get("sha256") == record["sha256"]:
            record["reasons"] = ["exact duplicate of a recently published source"]
            return record
        if near_duplicate(hashes, old.get("frame_hashes") or [], config["DUPLICATE_HASH_DISTANCE"]):
            record["reasons"] = ["near duplicate of a recently published source"]
            return record
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    age_days = max(0, (now - record["published_utc"]) / 86400) if record["published_utc"] else None
    visual = min(1.0, min(media["width"], media["height"]) / 1080) * 0.65 + min(1.0, media["fps"] / 30) * 0.35
    engagement = min(1.0, (math.log1p(_number(post.get("score"))) / math.log1p(1500)) * 0.7
                     + (math.log1p(_number(post.get("num_comments"))) / math.log1p(150)) * 0.3)
    recency = max(0.0, 1.0 - age_days / 365) if age_days is not None else None
    useful = min(1.0, media["duration"] / 20) if media["duration"] < 90 else max(0.4, 1 - (media["duration"] - 90) / 180)
    compatibility = 1.0 if media["aspect_ratio"] < 0.8 else 0.75 if media["aspect_ratio"] <= 1.0 else 0.55
    factors: dict[str, float | None] = {
        "visual": visual, "engagement": engagement if post.get("score_available", post.get("score") is not None) else None,
        "recency": recency, "duration": useful, "uniqueness": 1.0, "format": compatibility,
    }
    weights = config["SOURCE_WEIGHTS"]
    available = sum(weights[key] for key, value in factors.items() if value is not None)
    record["score"] = round(100 * sum(weights[key] * value for key, value in factors.items() if value is not None) / available)
    record["factors"] = {key: round(value, 3) if value is not None else None for key, value in factors.items()}
    record["reasons"] = [f"{key}: {record['factors'][key]}" for key in factors if factors[key] is not None]
    record["accepted"] = record["score"] >= config["MIN_SOURCE_SCORE"]
    if not record["accepted"]:
        record["reasons"].append(f"score below {config['MIN_SOURCE_SCORE']}")
    return record


def select_sources(records: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for record in sorted((item for item in records if item["accepted"]),
                         key=lambda item: (item["score"], item["duration"]), reverse=True):
        if any(record["sha256"] == old["sha256"] or near_duplicate(
            record["frame_hashes"], old["frame_hashes"], config["DUPLICATE_HASH_DISTANCE"]
        ) for old in selected):
            record["accepted"] = False
            record["reasons"].append("duplicate within this video")
            continue
        selected.append(record)
        if len(selected) >= config["MAX_SOURCE_COUNT"]:
            break
    return selected


def plan_shots(
    sources: list[dict[str, Any]], duration: float, config: dict[str, Any], *, seed: str,
    template: str = "strongest_visual",
) -> list[dict[str, Any]]:
    if len(sources) < config["MIN_SOURCE_COUNT"]:
        raise QualityError("insufficient distinct sources")
    if template not in {"strongest_visual", "hook_body_payoff", "comparison", "timeline"}:
        raise QualityError(f"unknown deterministic edit template: {template}")
    rng = random.Random(seed)
    cursors = {item["source_id"]: min(1.2, max(0.0, item["duration"] - 3))
               if item.get("opening_luma", 255) < 16 or item.get("opening_motion", 1) < 0.03 else 0.0
               for item in sources}
    used = {item["source_id"]: 0.0 for item in sources}
    shots: list[dict[str, Any]] = []
    remaining = duration
    while remaining > 0.02:
        elapsed = duration - remaining
        cap = config["HOOK_CLIP_MAX"] if not shots else (
            config["EARLY_CLIP_MAX"] if elapsed < 5 else
            min(config["ABSOLUTE_CLIP_MAX"], config["NORMAL_CLIP_MAX"] + 1)
            if remaining < 8 else config["NORMAL_CLIP_MAX"])
        cap = min(cap, config["ABSOLUTE_CLIP_MAX"])
        target = min(remaining, cap * rng.uniform(0.70, 1.0))
        if remaining <= cap:
            target = remaining
        available = {
            item["source_id"]: min(
                item["duration"] - cursors[item["source_id"]] - 0.1,
                duration * config["MAX_SINGLE_SOURCE_PERCENT"] / 100 - used[item["source_id"]],
            ) for item in sources
        }
        eligible = [item for item in sources if available[item["source_id"]] > 0.05]
        if not shots:
            hook_ready = [item for item in eligible if item.get("hook_suitable", True)]
            if not hook_ready:
                raise QualityError("no motion-filled, non-black opening clip")
            eligible = hook_ready
        if shots:
            alternate = [item for item in eligible if item["source_id"] != shots[-1]["source_id"]]
            eligible = alternate or eligible
            if remaining <= cap:
                different_ending = [item for item in eligible if item["source_id"] != shots[0]["source_id"]]
                if not different_ending:
                    raise QualityError("ending would repeat the hook source")
                eligible = different_ending
        if not eligible:
            raise QualityError("not enough unique unlooped footage for the requested duration")
        full_shot = [item for item in eligible if available[item["source_id"]] >= target]
        eligible = full_shot or eligible
        timeline = sorted(sources, key=lambda item: item.get("published_utc") or 0)
        timeline_target = min(len(timeline) - 1, int(elapsed / max(duration, 1) * len(timeline)))
        top_two = sorted(sources, key=lambda item: item["score"], reverse=True)[:2]
        def preference(item: dict[str, Any]) -> tuple[float, float]:
            bonus = 0.0
            if template == "hook_body_payoff":
                bonus = item.get("opening_motion", 0) * (35 if remaining < 8 else 12)
            elif template == "comparison" and top_two:
                bonus = 20 if item["source_id"] == top_two[len(shots) % len(top_two)]["source_id"] else 0
            elif template == "timeline":
                bonus = 18 if item["source_id"] == timeline[timeline_target]["source_id"] else 0
            return (item["score"] - used[item["source_id"]] * 2 + bonus
                    + (item.get("opening_motion", 0) * 30 if not shots else 0),
                    available[item["source_id"]])
        source = max(eligible, key=preference)
        source_id = source["source_id"]
        target = min(target, available[source_id])
        if target < 0.1:
            raise QualityError("remaining source footage is too fragmented")
        shots.append({"source_id": source_id, "path": source["path"],
                      "start": round(cursors[source_id], 3), "duration": round(target, 3)})
        cursors[source_id] += target + 0.1
        used[source_id] += target
        remaining -= target
        if len(shots) > 60:
            raise QualityError("pacing planner exceeded its shot limit")
    return shots


def caption_issues(path: Path, duration: float) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if r"\pos(540,1120)" not in text:
        return ["captions are outside the configured safe position"]
    times: list[tuple[float, float]] = []
    for line in text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            return ["malformed subtitle event"]
        def seconds(value: str) -> float:
            hours, minutes, rest = value.split(":")
            return int(hours) * 3600 + int(minutes) * 60 + float(rest)
        times.append((seconds(parts[1]), seconds(parts[2])))
    if not times:
        return ["no subtitle events"]
    if any(end <= start or end > duration + 0.05 or (index and start < times[index - 1][1] - 0.011)
           for index, (start, end) in enumerate(times)):
        return ["subtitle timing invalid or overlapping"]
    return []


def final_media_issues(path: Path, config: dict[str, Any], *, minimum_duration: float) -> tuple[dict[str, Any], list[str]]:
    media = probe_media(path)
    issues: list[str] = []
    if media["duration"] < minimum_duration - 0.5:
        issues.append("final video too short")
    if media["file_size"] < 100_000 or media["width"] != 1080 or media["height"] != 1920:
        issues.append("final output size or aspect ratio invalid")
    if not media["has_audio"]:
        issues.append("final video has no audio")
    if issues:
        return media, issues
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af",
         f"silencedetect=noise=-35dB:d={config['MAX_SILENCE_SECONDS']},volumedetect",
         "-vn", "-f", "null", "-"], text=True, capture_output=True,
    )
    if result.returncode != 0:
        return media, ["final audio validation failed"]
    silence = re.search(r"silence_duration:\s*([\d.]+)", result.stderr)
    mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", result.stderr)
    peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", result.stderr)
    if silence and float(silence.group(1)) > config["MAX_SILENCE_SECONDS"]:
        issues.append("long final-audio silence")
    if not mean or float(mean.group(1)) < config["MIN_AUDIO_MEAN_DB"]:
        issues.append("final audio is too quiet")
    if not peak or float(peak.group(1)) > config["MAX_AUDIO_PEAK_DB"]:
        issues.append("final audio peak is too high")
    black = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
         f"blackdetect=d={config['MAX_BLACK_SECONDS']}:pix_th=0.10", "-an", "-f", "null", "-"],
        text=True, capture_output=True,
    )
    if black.returncode != 0:
        issues.append("final black-frame validation failed")
    elif any(float(value) > config["MAX_BLACK_SECONDS"] for value in
             re.findall(r"black_duration:([\d.]+)", black.stderr)):
        issues.append("long black section in final video")
    return media, issues


def build_report(
    video_id: str, records: list[dict[str, Any]], selected: list[dict[str, Any]],
    shots: list[dict[str, Any]], duration: float, config: dict[str, Any],
    *, final_issues: list[str] | None = None,
) -> dict[str, Any]:
    reasons = list(final_issues or [])
    selected_ids = {item["source_id"] for item in selected}
    duplicates = [item["source_url"] for item in records if any("duplicate" in reason for reason in item["reasons"])]
    shot_durations = [shot["duration"] for shot in shots]
    longest = max(shot_durations, default=0)
    if len(selected) < config["MIN_SOURCE_COUNT"]:
        reasons.append(f"only {len(selected)} of {config['MIN_SOURCE_COUNT']} required distinct sources")
    if not shots:
        reasons.append("no valid pacing plan")
    if longest > config["ABSOLUTE_CLIP_MAX"] + 0.02:
        reasons.append("shot exceeds absolute pacing limit")
    if selected and shots:
        for source_id in selected_ids:
            share = 100 * sum(shot["duration"] for shot in shots if shot["source_id"] == source_id) / duration
            if share > config["MAX_SINGLE_SOURCE_PERCENT"] + 0.1:
                reasons.append(f"source {source_id} dominates {share:.1f}% of the video")
    source_quality = sum(item["score"] for item in selected) / len(selected) if selected else 0
    factors = {
        "source_quality": 20 * source_quality / 100,
        "source_diversity": 15 * min(1, len(selected) / max(1, config["MIN_SOURCE_COUNT"])),
        "duplicate_avoidance": 15 if not duplicates else 8,
        "opening_quality": 15 if shots and any(
            item["source_id"] == shots[0]["source_id"] and item.get("hook_suitable", True)
            for item in selected) else 4,
        "pacing": 15 if shots and not any("shot exceeds" in reason for reason in reasons) else 0,
        "audio_validity": 10 if not any("audio" in reason for reason in reasons) else 0,
        "subtitle_layout": 5 if not any("subtitle" in reason for reason in reasons) else 0,
        "technical_integrity": 5 if not any("final video" in reason or "output" in reason for reason in reasons) else 0,
    }
    score = round(sum(factors.values()))
    if score < config["MIN_FINAL_SCORE"]:
        reasons.append(f"final score {score} below {config['MIN_FINAL_SCORE']}")
    decision = "publish" if not reasons else "reject"
    return {
        "video_id": video_id, "sources_considered": len(records), "sources_used": len(selected),
        "selected_source_ids": [item["source_id"] for item in selected],
        "source_scores": [{key: value for key, value in record.items() if key != "path"} for record in records],
        "duplicate_sources_rejected": duplicates,
        "final_duration": round(duration, 3),
        "average_clip_duration": round(sum(shot_durations) / len(shots), 3) if shots else 0,
        "longest_clip_duration": round(longest, 3),
        "final_quality_score": score, "score_components": {key: round(value, 2) for key, value in factors.items()},
        "decision": decision, "reasons": reasons,
        "pacing": [{key: value for key, value in shot.items() if key != "path"} for shot in shots],
    }


def write_report(report: dict[str, Any], directory: Path = REPORT_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report['video_id']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"FINAL QUALITY SCORE: {report['final_quality_score']}/100 | {report['decision'].upper()}")
    print(f"SELECTED SOURCES: {', '.join(report['selected_source_ids']) or 'none'}")
    print(f"PACING: {len(report['pacing'])} shots, average {report['average_clip_duration']:.2f}s, "
          f"longest {report['longest_clip_duration']:.2f}s")
    for reason in report["reasons"]:
        print(f"QUALITY REASON: {reason}")
    for record in report["source_scores"]:
        print(f"SOURCE SCORE: {record['source_id']} {record['score']}/100 "
              f"{'accepted' if record['accepted'] else 'rejected'} — {', '.join(record['reasons'])}")
    return path
