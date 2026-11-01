#!/usr/bin/env python3
"""Deterministic story, verification, template, caption, metadata, and state engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "bl_automation.json"
MANIFEST_PATH = ROOT / "templates" / "manifest.json"
METADATA_PATH = ROOT / "templates" / "metadata.json"
STATE_PATH = ROOT / "data" / "bl_state.json"
PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
WORD = re.compile(r"[a-z0-9]+")


class BLEngineError(RuntimeError):
    """A deterministic validation or generation step failed."""


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BLEngineError(f"Unable to read JSON {path}: {exc}") from exc


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, suffix=".tmp") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def default_state() -> dict[str, Any]:
    return {"version": 2, "template_history": [], "hook_history": [], "layout_history": [],
            "title_pattern_history": [], "category_counts": {}, "published": []}


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return default_state()
    state = read_json(path)
    if not isinstance(state, dict) or state.get("version") != 2:
        raise BLEngineError("BL state must be a version 2 object")
    base = default_state()
    for key, value in base.items():
        state.setdefault(key, value)
    return state


def load_catalogs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config, manifest, metadata = read_json(CONFIG_PATH), read_json(MANIFEST_PATH), read_json(METADATA_PATH)
    templates = manifest.get("templates") if isinstance(manifest, dict) else None
    if not isinstance(templates, list) or len(templates) < 100:
        raise BLEngineError("Template manifest must contain at least 100 templates")
    ids = [item.get("id") for item in templates if isinstance(item, dict)]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        raise BLEngineError("Template IDs must be present and unique")
    layout_ids = {item.get("id") for item in config.get("layouts", [])}
    if len(layout_ids) < 15:
        raise BLEngineError("At least 15 visual layouts are required")
    for template in templates:
        if template.get("scene_layout") not in layout_ids:
            raise BLEngineError(f"Unknown layout in template {template.get('id')}")
        if template.get("caption_profile") not in config.get("caption_profiles", {}):
            raise BLEngineError(f"Unknown caption profile in template {template.get('id')}")
    return config, manifest, metadata


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalized_url(value: str) -> str:
    parsed = urlparse(clean_text(value))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", "", ""))


def normalized_headline(value: str) -> str:
    return " ".join(WORD.findall(clean_text(value).casefold()))


def content_fingerprint(story: dict[str, Any]) -> str:
    material = "|".join([
        normalized_headline(story.get("headline", "")), clean_text(story.get("category")).casefold(),
        clean_text(story.get("actor")).casefold(), clean_text(story.get("actor_2")).casefold(),
        clean_text(story.get("series")).casefold(), clean_text(story.get("event")).casefold(),
        clean_text(story.get("date") or story.get("release_date")).casefold(),
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def story_id_for(story: dict[str, Any]) -> str:
    explicit = re.sub(r"[^a-zA-Z0-9_-]+", "-", clean_text(story.get("story_id"))).strip("-")
    return explicit[:80] or content_fingerprint(story)[:20]


def source_score(story: dict[str, Any], config: dict[str, Any]) -> tuple[int, list[str]]:
    rules = config["verification"]
    sources = story.get("sources") or []
    if not isinstance(sources, list) or not sources:
        return 0, ["no source records"]
    scores = rules["scores"]
    classes = [clean_text(item.get("type")).casefold() for item in sources if isinstance(item, dict)]
    base = max((int(scores.get(kind, scores["unknown"])) for kind in classes), default=0)
    reasons = [f"best source class: {classes[classes.index(max(classes, key=lambda k: scores.get(k, 0)))]}" if classes else "unknown source"]
    reputable_count = sum(kind in {"official", "reputable_media"} for kind in classes)
    if reputable_count >= 2:
        base += int(rules["second_reputable_bonus"])
        reasons.append("second reputable source")
    if story.get("official_confirmation") or "official" in classes:
        base += int(rules["official_confirmation_bonus"])
        reasons.append("official confirmation")
    dates = {clean_text(item.get("event_date") or item.get("date")) for item in sources if isinstance(item, dict)} - {""}
    if story.get("matching_event_information") or len(dates) == 1 and len(sources) >= 2:
        base += int(rules["matching_event_bonus"])
        reasons.append("matching date/event information")
    return min(100, base), reasons


def sensitive_reasons(story: dict[str, Any], config: dict[str, Any]) -> list[str]:
    text = " ".join(clean_text(story.get(key)) for key in ("headline", "event", "context", "detail", "official_statement")).casefold()
    declared = [clean_text(value).casefold() for value in story.get("sensitive_topics", [])]
    return sorted({term for term in config["verification"]["sensitive_topics"] if term in text or term in declared})


def verification_result(story: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    score, reasons = source_score(story, config)
    sensitive = sensitive_reasons(story, config)
    if sensitive:
        decision = "manual_review"
        reasons.append("sensitive claim requires manual review: " + ", ".join(sensitive))
    elif score >= config["verification"]["auto_publish_minimum"]:
        decision = "auto_publish"
    elif score >= config["verification"]["manual_review_minimum"]:
        decision = "manual_review"
    else:
        decision = "reject"
    return {"score": score, "decision": decision, "reasons": reasons, "sensitive_topics": sensitive}


def validate_story(story: dict[str, Any], config: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors = []
    if not isinstance(story, dict):
        return ["story must be a JSON object"]
    category = clean_text(story.get("category"))
    categories = {item["category"] for item in manifest["templates"]}
    if category not in categories:
        errors.append(f"unsupported category: {category or '(blank)'}")
    if not clean_text(story.get("headline")):
        errors.append("headline is required")
    sources = story.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("at least one source is required")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, dict) or not normalized_url(source.get("url", "")):
                errors.append(f"source {index + 1} needs a valid URL")
            if clean_text((source or {}).get("type")) not in config["verification"]["scores"]:
                errors.append(f"source {index + 1} has an unsupported type")
    assets = story.get("assets", [])
    if not isinstance(assets, list):
        errors.append("assets must be an array")
    for index, asset in enumerate(assets if isinstance(assets, list) else []):
        if not isinstance(asset, dict) or not clean_text(asset.get("path") or asset.get("url")):
            errors.append(f"asset {index + 1} needs path or URL")
        elif not bool(asset.get("authorized")):
            errors.append(f"asset {index + 1} is not marked authorized")
    return errors


def duplicate_reasons(story: dict[str, Any], state: dict[str, Any]) -> list[str]:
    story_id = story_id_for(story)
    urls = {normalized_url(item.get("url", "")) for item in story.get("sources", [])} - {""}
    headline_hash = hashlib.sha256(normalized_headline(story.get("headline", "")).encode()).hexdigest()
    fingerprint = content_fingerprint(story)
    reasons = []
    for published in state.get("published", []):
        if published.get("story_id") == story_id:
            reasons.append("story_id already published")
        if urls & set(published.get("source_urls", [])):
            reasons.append("source URL already published")
        if published.get("headline_hash") == headline_hash:
            reasons.append("normalized headline already published")
        if published.get("content_fingerprint") == fingerprint:
            reasons.append("content fingerprint already published")
    return sorted(set(reasons))


def seed_number(story_id: str, label: str = "") -> int:
    return int(hashlib.sha256(f"{story_id}|{label}".encode()).hexdigest()[:16], 16)


def choose_template(story: dict[str, Any], state: dict[str, Any], config: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    fields = {key for key, value in story.items() if clean_text(value) if not isinstance(value, (list, dict))}
    candidates = [item for item in manifest["templates"] if item["category"] == story["category"] and set(item.get("required_fields", [])) <= fields]
    if not candidates:
        missing_sets = [set(item.get("required_fields", [])) - fields for item in manifest["templates"] if item["category"] == story["category"]]
        missing = min(missing_sets, key=len) if missing_sets else set()
        raise BLEngineError("Story lacks fields for its category: " + ", ".join(sorted(missing)))
    rotation = config["rotation"]
    recent_templates = set(state["template_history"][-rotation["template_cooldown"]:])
    recent_hooks = set(state["hook_history"][-rotation["hook_cooldown"]:])
    recent_layouts = set(state["layout_history"][-rotation["layout_cooldown"]:])
    def rank(item: dict[str, Any]) -> tuple[int, int, int, int]:
        return (item["id"] in recent_templates, item["hook_pattern"] in recent_hooks,
                item["scene_layout"] in recent_layouts, seed_number(story_id_for(story), item["id"]))
    return min(candidates, key=rank)


def substitute_line(line: str, story: dict[str, Any], required: set[str]) -> str:
    fields = PLACEHOLDER.findall(line)
    missing = [field for field in fields if not clean_text(story.get(field))]
    if missing:
        if any(field in required for field in missing):
            raise BLEngineError("Missing required template value: " + ", ".join(missing))
        return ""
    rendered = PLACEHOLDER.sub(lambda match: clean_text(story.get(match.group(1))), line)
    return re.sub(r"\s+([.,!?;:])", r"\1", clean_text(rendered))


def split_captions(text: str, *, max_chars: int = 32, max_lines: int = 2) -> list[str]:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", clean_text(text)) if part.strip()]
    captions: list[str] = []
    for sentence in sentences:
        chunks = textwrap.wrap(sentence, width=max_chars * max_lines, break_long_words=False, break_on_hyphens=False) or [sentence]
        for chunk in chunks:
            lines = textwrap.wrap(chunk, width=max_chars, break_long_words=False, break_on_hyphens=False)
            if len(lines) > max_lines:
                midpoint = max(1, len(chunk.split()) // 2)
                words = chunk.split()
                lines = [" ".join(words[:midpoint]), " ".join(words[midpoint:])]
            captions.append("\n".join(lines[:max_lines]))
    return captions


def choose_catalog_item(items: list[Any], story_id: str, label: str, recent: Iterable[int] = ()) -> tuple[int, Any]:
    order = sorted(range(len(items)), key=lambda index: seed_number(story_id, f"{label}:{index}"))
    recent_set = set(recent)
    index = next((index for index in order if index not in recent_set), order[0])
    return index, items[index]


def generate_package(story: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    config, manifest, metadata_catalog = load_catalogs()
    errors = validate_story(story, config, manifest)
    if errors:
        raise BLEngineError("; ".join(errors))
    state = state or load_state()
    verification = verification_result(story, config)
    duplicates = duplicate_reasons(story, state)
    if duplicates:
        raise BLEngineError("Duplicate blocked: " + "; ".join(duplicates))
    template = choose_template(story, state, config, manifest)
    required = set(template["required_fields"])
    hook = substitute_line(template["hook"], story, required)
    body = [value for value in (substitute_line(line, story, required) for line in template["body"]) if value]
    cta = substitute_line(template["cta"], story, required)
    narration = " ".join([hook, *body, cta])
    unresolved = PLACEHOLDER.findall(narration)
    if unresolved:
        raise BLEngineError("Unresolved placeholders: " + ", ".join(sorted(set(unresolved))))
    story_id = story_id_for(story)
    profile = config["caption_profiles"][template["caption_profile"]]
    captions = split_captions(narration, max_chars=profile["max_chars"], max_lines=profile["max_lines"])
    title_recent = state.get("title_pattern_history", [])[-10:]
    title_index, title_pattern = choose_catalog_item(metadata_catalog["title_patterns"], story_id, "title", title_recent)
    title = substitute_line(title_pattern, story, set()) or clean_text(story["headline"])
    description_index, description_pattern = choose_catalog_item(metadata_catalog["description_templates"], story_id, "description")
    description_lead = substitute_line(description_pattern, story, set()) or clean_text(story["headline"])
    hashtag_index, hashtags = choose_catalog_item(metadata_catalog["hashtag_sets"], story_id, "hashtags")
    source_lines = [f"- {clean_text(item.get('name')) or item['type']}: {normalized_url(item['url'])}" for item in story["sources"]]
    description = description_lead + "\n\nSources:\n" + "\n".join(source_lines) + f"\n\nStory ID: {story_id}\n" + " ".join(hashtags)
    duration = max(config["target"]["min_seconds"], min(config["target"]["max_seconds"], template["duration_target"]))
    layout = next(item for item in config["layouts"] if item["id"] == template["scene_layout"])
    return {
        "story": story, "story_id": story_id, "template": template, "layout": layout,
        "verification": verification, "duplicate_check": {"passed": True, "reasons": []},
        "script": {"hook": hook, "body": body, "cta": cta, "narration": narration, "captions": captions},
        "render": {"duration_target": duration, "caption_profile": profile, "music_profile": config["music_profiles"][template["music_profile"]], "seed": seed_number(story_id)},
        "metadata": {"title": title[:100], "description": description, "tags": [tag.lstrip("#") for tag in hashtags], "category_id": "24", "made_for_kids": False, "privacy_status": clean_text(story.get("privacy_status")) or "public", "format": "bl_entertainment_short", "story_id": story_id, "template_id": template["id"], "layout_id": layout["id"], "source_urls": [normalized_url(item["url"]) for item in story["sources"]]},
        "catalog_choices": {"title_pattern": title_index, "description_template": description_index, "hashtag_set": hashtag_index},
    }


def record_success(package: dict[str, Any], state: dict[str, Any], *, youtube_video_id: str = "") -> dict[str, Any]:
    config = read_json(CONFIG_PATH)
    template, story = package["template"], package["story"]
    state["template_history"].append(template["id"])
    state["hook_history"].append(template["hook_pattern"])
    state["layout_history"].append(template["scene_layout"])
    state["title_pattern_history"].append(package["catalog_choices"]["title_pattern"])
    state["category_counts"][story["category"]] = state["category_counts"].get(story["category"], 0) + 1
    state["published"].append({
        "story_id": package["story_id"], "source_urls": package["metadata"]["source_urls"],
        "headline_hash": hashlib.sha256(normalized_headline(story["headline"]).encode()).hexdigest(),
        "content_fingerprint": content_fingerprint(story), "template_id": template["id"],
        "layout_id": template["scene_layout"], "published_at": datetime.now(timezone.utc).isoformat(),
        "youtube_video_id": youtube_video_id,
    })
    limit = config["rotation"]["history_limit"]
    for key in ("template_history", "hook_history", "layout_history", "title_pattern_history", "published"):
        state[key] = state[key][-limit:]
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "package.json")
    parser.add_argument("--allow-review", action="store_true", help="Generate review packages, never grants auto-publish")
    args = parser.parse_args()
    story = read_json(args.input)
    package = generate_package(story)
    if package["verification"]["decision"] != "auto_publish" and not args.allow_review:
        raise SystemExit(f"NOT AUTO-PUBLISHABLE: {package['verification']}")
    write_json_atomic(args.output, package)
    print(f"Generated {package['story_id']} with {package['template']['id']} / {package['layout']['id']}")


if __name__ == "__main__":
    try:
        main()
    except BLEngineError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
