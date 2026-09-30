from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import audio
from .assets import generate_cards, load_approved_assets
from .config import load_config
from .models import ProductionManifest, Topic
from .media_timeline import build_timeline
from .music import ensure_original_theme
from .quality import validate
from .research import collect
from .scripts import generate_script, publication_script_errors
from .state import atomic_write, load_state, queue_manifest
from .topics import rank_topics
from .video import render
from src.utils import safe_filename


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _job(manifest: dict[str, Any], privacy: str) -> dict[str, Any]:
    script = manifest["script"]
    return {
        "job_id": manifest["content_id"], "title": script["title"], "description": script["description"],
        "tags": script["tags"], "privacy_status": privacy, "thumbnail_file": "",
        "source_video_id": manifest["topic"]["topic_id"],
    }


def _eligible(topic: Topic) -> bool:
    domains = {source.publisher for source in topic.sources}
    official = any(source.source_kind == "official" and source.reliability >= 3 for source in topic.sources)
    trusted_report = any(source.reliability >= 2 and source.source_kind in {"entertainment_news", "trade_press", "broadcaster", "government"}
                         for source in topic.sources)
    return not topic.review_reason and all(source.rights == "facts_only" for source in topic.sources) and (official or len(domains) >= 2 or trusted_report)


def _render_topic(root: Path, config: dict[str, Any], topic: Topic, content_id: str,
                  slot_id: str, existing_script: dict[str, Any] | None = None,
                  require_originality: bool = False, discover_live_media: bool = True) -> dict[str, Any]:
    output = root / "output"
    output.mkdir(exist_ok=True)
    target_words = int(config["content"].get("target_words", 90))
    script = existing_script or generate_script(topic, target_words)
    if not 65 <= script["word_count"] <= 100:
        raise ValueError(f"insufficient independently sourced detail for a 65-word Short ({script['word_count']} words)")
    narration = output / "narration.mp3"
    timings_path = output / "word-timings.json"
    timings, seconds = audio.synthesize(
        script["narration"], narration, timings_path,
        config["video"]["voice"], config["video"].get("voice_rate", "+5%"),
    )
    maximum = float(config["content"]["maximum_seconds"]) - 0.55
    if seconds > maximum:
        reduced = max(65, int(script["word_count"] * maximum / seconds * 0.92))
        script = generate_script(topic, reduced)
        if require_originality and publication_script_errors(topic, script):
            raise RuntimeError("fitted narration no longer meets publication checks")
        timings, seconds = audio.synthesize(
            script["narration"], narration, timings_path,
            config["video"]["voice"], config["video"].get("voice_rate", "+5%"),
        )
    if seconds > maximum:
        raise RuntimeError(f"narration remains too long after fitting: {seconds:.2f}s")
    load_approved_assets(root)  # Fail closed if a user-supplied license record is malformed.
    cards = generate_cards(topic.to_dict(), script, output / "scenes")
    assets, media_errors = build_timeline(root, topic, config, cards, content_id, discover_live_media)
    video_config = dict(config["video"])
    music = str(video_config.get("background_music") or "")
    if music:
        music_path = (root / music).resolve()
        if root.resolve() not in music_path.parents:
            raise ValueError("background music path must stay inside the repository")
        if music_path.name == "lululala-theme.wav":
            ensure_original_theme(music_path)
        elif not music_path.is_file():
            raise FileNotFoundError("licensed background music is missing")
        video_config["background_music"] = str(music_path)
    production = render(assets, narration, timings, script, output, seconds, video_config)
    quality = validate(
        topic.to_dict(), script, assets, Path(production["path"]),
        float(config["content"]["minimum_seconds"]), float(config["content"]["maximum_seconds"]),
        require_originality=require_originality,
    )
    status = "pending_approval" if quality["valid"] else "quality_failed"
    manifest = ProductionManifest(
        content_id=content_id, slot_id=slot_id, created_at=datetime.now(timezone.utc).isoformat(),
        status=status, topic=topic.to_dict(), script=script, assets=assets, quality=quality,
    ).to_dict()
    manifest["media_errors"] = media_errors
    _write(output / "manifest.json", manifest)
    _write(output / "quality-report.json", quality)
    _write(output / "job.json", _job(manifest, str(config["channel"]["upload_privacy"])))
    if not quality["valid"]:
        raise RuntimeError("quality control rejected render: " + "; ".join(quality["errors"]))
    name = datetime.now(timezone.utc).strftime("%Y-%m-%d") + "_" + safe_filename(topic.entity + "_" + topic.title)
    for folder, filename, source in (
        ("scripts", name + ".txt", output / "transcript.txt"),
        ("audio", content_id + ".mp3", narration),
        ("videos", content_id + ".mp4", output / "short.mp4"),
    ):
        target = output / folder / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return manifest


def produce(root: Path, config_path: Path, slot_id: str, category: str = "",
            dry_run: bool = False, fixture: Path | None = None) -> dict[str, Any]:
    config = load_config(config_path)
    state_path = root / "data" / "kpop_state.json"
    state = load_state(state_path)
    if not dry_run and slot_id in state.get("slots", {}):
        result = {"action": "duplicate_slot", "slot_id": slot_id, "content_id": state["slots"][slot_id],
                  "should_publish": False}
        _write(root / "output" / "result.json", result)
        return result
    research_errors: list[dict[str, str]] = []
    if fixture:
        if not dry_run:
            raise ValueError("test fixtures are permitted only with --dry-run")
        topic = Topic.from_dict(json.loads(fixture.read_text(encoding="utf-8")))
    else:
        records, research_errors = collect(config)
        topics = rank_topics(records, state, config, category)
        _write(root / "data" / "news.json", [
            {"id": item.source_id, "celebrity_name": item.entities[0], "headline": item.title, "source": item.publisher,
             "source_url": item.url, "published_at": item.published_at, "summary": item.evidence,
             "category": item.category, "keywords": list(item.entities) + item.title.split()[:6]} for item in records
        ])
        _write(root / "data" / "unique_news.json", [item.to_dict() for item in topics])
        _write(root / "data" / "deferred_topics.json", [item.to_dict() for item in topics if 60 <= item.score < 75])
        _write(root / "data" / "verified_topics.json", [item.to_dict() for item in topics if not item.review_reason])
        publishable = [item for item in topics if not item.review_reason]
        sufficiently_detailed = [
            item for item in publishable
            if not publication_script_errors(
                item, generate_script(item, int(config["content"].get("target_words", 90)))
            )
        ]
        if not sufficiently_detailed:
            result = {"action": "no_verified_topic", "slot_id": slot_id, "research_errors": research_errors,
                      "review_candidates": len(topics), "verified_candidates": len(publishable),
                      "reason": "no current verified story supports an original 65–100-word script without an API",
                      "should_publish": False}
            _write(root / "output" / "result.json", result)
            return result
        topic = sufficiently_detailed[0]
    content_id = hashlib.sha256(f"{slot_id}|{topic.topic_id}".encode()).hexdigest()[:20]
    if topic.review_reason:
        result = {"action": "research_review", "slot_id": slot_id, "content_id": content_id,
                  "reason": topic.review_reason, "topic": topic.to_dict(), "should_publish": False}
        _write(root / "output" / "result.json", result)
        return result
    manifest = _render_topic(root, config, topic, content_id, slot_id,
                             require_originality=fixture is None,
                             discover_live_media=fixture is None)
    manifest["research_errors"] = research_errors
    _write(root / "output" / "manifest.json", manifest)
    if not dry_run:
        queue_manifest(state, manifest)
        atomic_write(state_path, state)
        atomic_write(root / "data" / "manifests" / f"{content_id}.json", manifest)
    should_publish = (bool(config["channel"]["auto_publish"]) and _eligible(topic) and not dry_run
                      and not publication_script_errors(topic, manifest["script"])
                      and manifest["quality"].get("originality_score", 0) >= 80)
    result = {"action": "rendered", "content_id": content_id, "slot_id": slot_id,
              "status": manifest["status"], "should_publish": should_publish,
              "privacy": config["channel"]["upload_privacy"], "video": str(root / "output" / "short.mp4")}
    _write(root / "output" / "result.json", result)
    return result


def render_pending(root: Path, config_path: Path, content_id: str) -> dict[str, Any]:
    config = load_config(config_path)
    path = root / "data" / "manifests" / f"{content_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"pending manifest not found: {content_id}")
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved["status"] not in {"pending_approval", "approved"}:
        raise ValueError(f"content cannot be approved from status {saved['status']}")
    topic = Topic.from_dict(saved["topic"])
    if not _eligible(topic):
        raise ValueError("topic is not eligible for publishing")
    if publication_script_errors(topic, saved["script"]):
        raise ValueError("pending script does not meet no-API publication checks")
    return _render_topic(root, config, topic, content_id, saved["slot_id"], saved["script"],
                         require_originality=True)
