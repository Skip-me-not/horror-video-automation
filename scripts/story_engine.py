#!/usr/bin/env python3
"""Quality, pacing, hook selection, and anti-repetition for micro-stories."""

from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MIN_SECONDS = 25.0
MAX_SECONDS = 40.0
WORDS_PER_SECOND = 2.65
RECENT_WINDOW = 30
SIMILARITY_LIMIT = 0.58
SUPPORTED_PILLARS = {
    "transformation",
    "failure_comeback",
    "relatable_pain",
    "future_self",
    "disappear_rebuild",
    "hard_truth_story",
}
SUPPORTED_PERSPECTIVES = {"he", "she", "you", "first_person", "unnamed", "future_self"}
REQUIRED_FIELDS = {
    "id",
    "pillar",
    "topic",
    "theme",
    "perspective",
    "protagonist",
    "hook_type",
    "hook_candidates",
    "hook_visual",
    "beats",
    "title_candidates",
    "ending_concept",
    "key_phrases",
    "music_searches",
}
GENERIC_OPENINGS = (
    "never give up",
    "believe in yourself",
    "work hard in silence",
    "you need to hear this",
    "this will change your life",
    "here is your daily motivation",
    "success requires sacrifice",
)
CLICHE_PAYOFFS = (
    "anything is possible",
    "never give up",
    "believe in yourself",
    "dreams come true",
    "the sky is the limit",
    "success is the best revenge",
)
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "been", "but", "by",
    "for", "from", "had", "has", "have", "he", "her", "him", "his", "i", "in",
    "is", "it", "its", "of", "on", "or", "she", "so", "that", "the", "their",
    "them", "then", "they", "this", "to", "was", "were", "when", "with", "you",
    "your",
}


class StoryError(RuntimeError):
    """A catalog or story failed a user-actionable quality rule."""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9$']+", text))


def seconds_to_ass(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    whole_seconds, hundredths = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{hundredths:02d}"


def hook_score(hook: str) -> float:
    """Score concrete, clear, emotionally open-looped hooks."""
    text = clean_text(hook)
    lower = text.casefold()
    words = word_count(text)
    score = 0.0
    if 6 <= words <= 16:
        score += 3.0
    elif words <= 20:
        score += 1.0
    else:
        score -= 2.0
    if re.search(r"(?:\$\d+|\b\d{1,3}(?::\d{2})?\b|\b\d{4}\b)", text):
        score += 3.0
    if any(term in lower for term in ("rent", "rejected", "behind", "deleted", "empty", "failed", "left", "due", "again", "still", "nothing")):
        score += 2.0
    if any(term in lower for term in ("but", "until", "then", "only", "last", "finally")):
        score += 1.0
    if text.endswith("?"):
        score += 0.5
    if any(generic in lower for generic in GENERIC_OPENINGS):
        score -= 10.0
    if not text or text[-1] not in ".?!":
        score -= 0.5
    return score


def select_hook(story: dict[str, Any]) -> str:
    hooks = [clean_text(value) for value in story["hook_candidates"]]
    return max(hooks, key=lambda value: (hook_score(value), -len(value)))


def title_score(title: str) -> float:
    text = clean_text(title)
    words = word_count(text)
    score = 0.0
    if 3 <= words <= 8:
        score += 3.0
    if len(text) <= 55:
        score += 2.0
    if any(term in text.casefold() for term in ("left", "behind", "stopped", "future", "again", "last", "disappeared", "started over")):
        score += 1.0
    if text.isupper() or "🔥" in text:
        score -= 5.0
    return score


def select_title(story: dict[str, Any]) -> str:
    titles = [clean_text(value) for value in story["title_candidates"]]
    return max(titles, key=lambda value: (title_score(value), -len(value)))


def story_beats(story: dict[str, Any], hook: str | None = None) -> list[dict[str, str]]:
    selected_hook = hook or select_hook(story)
    return [
        {
            "phase": "hook",
            "text": selected_hook,
            "visual_search": clean_text(story["hook_visual"]),
        },
        *[
            {
                "phase": clean_text(beat["phase"]),
                "text": clean_text(beat["text"]),
                "visual_search": clean_text(beat["visual_search"]),
            }
            for beat in story["beats"]
        ],
    ]


def estimate_beat_durations(beats: list[dict[str, str]]) -> list[float]:
    raw = [min(5.0, max(2.65, word_count(beat["text"]) / WORDS_PER_SECOND + 0.45)) for beat in beats]
    total = sum(raw)
    target = min(MAX_SECONDS, max(MIN_SECONDS, total))
    scale = target / total
    return [round(duration * scale, 3) for duration in raw]


def story_script(story: dict[str, Any], hook: str | None = None) -> str:
    return " ".join(beat["text"] for beat in story_beats(story, hook))


def normalize_story(item: Any, index: int = 0) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise StoryError(f"Story entry {index} must be an object")
    missing = sorted(REQUIRED_FIELDS - set(item))
    extra = sorted(set(item) - REQUIRED_FIELDS)
    if missing or extra:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise StoryError(f"Story entry {index} has invalid fields: {'; '.join(details)}")
    story = dict(item)
    for key in REQUIRED_FIELDS - {"hook_candidates", "beats", "title_candidates", "key_phrases", "music_searches"}:
        story[key] = clean_text(story[key])
    for key in ("hook_candidates", "title_candidates", "key_phrases", "music_searches"):
        if not isinstance(story[key], list):
            raise StoryError(f"Story {story.get('id', index)} field {key} must be a list")
        story[key] = [clean_text(value) for value in story[key]]
    if not isinstance(story["beats"], list):
        raise StoryError(f"Story {story.get('id', index)} beats must be a list")
    story["beats"] = [dict(beat) if isinstance(beat, dict) else beat for beat in story["beats"]]
    return story


def validate_story(story: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    story_id = clean_text(story.get("id", "unknown"))
    if story.get("pillar") not in SUPPORTED_PILLARS:
        errors.append(f"unsupported pillar {story.get('pillar')!r}")
    if story.get("perspective") not in SUPPORTED_PERSPECTIVES:
        errors.append(f"unsupported perspective {story.get('perspective')!r}")
    hooks = story.get("hook_candidates", [])
    if len(hooks) < 3 or len(set(value.casefold() for value in hooks)) != len(hooks):
        errors.append("needs at least three distinct hook candidates")
    if not story.get("title_candidates") or len(story["title_candidates"]) < 2:
        errors.append("needs at least two title candidates")
    if not story.get("key_phrases") or len(story["key_phrases"]) < 2:
        errors.append("needs at least two key phrases")
    if not story.get("music_searches"):
        errors.append("needs music search terms")
    try:
        hook = select_hook(story)
        beats = story_beats(story, hook)
    except (KeyError, TypeError, ValueError) as exc:
        return [f"invalid story structure: {exc}"]
    if not 7 <= len(beats) <= 10:
        errors.append(f"needs 7-10 information beats, found {len(beats)}")
    phases = [beat.get("phase") for beat in beats]
    for phase in ("hook", "problem", "turn", "payoff"):
        if phase not in phases:
            errors.append(f"missing {phase} phase")
    for beat_index, beat in enumerate(beats):
        if not beat.get("text") or not beat.get("visual_search"):
            errors.append(f"beat {beat_index} is missing text or visual search")
        if word_count(beat.get("text", "")) > 22:
            errors.append(f"beat {beat_index} exceeds 22 words")
    script = story_script(story, hook)
    duration = sum(estimate_beat_durations(beats))
    if not MIN_SECONDS <= duration <= MAX_SECONDS + 0.1:
        errors.append(f"estimated duration {duration:.1f}s is outside 25-40s")
    if not 55 <= word_count(script) <= 115:
        errors.append(f"script has {word_count(script)} words; expected 55-115")
    opening = hook.casefold()
    if any(generic in opening for generic in GENERIC_OPENINGS) or hook_score(hook) < 2:
        errors.append("selected hook is weak or generic")
    payoff = beats[-1]["text"].casefold()
    if beats[-1]["phase"] != "payoff":
        errors.append("last beat must be the payoff")
    if any(cliche in payoff for cliche in CLICHE_PAYOFFS):
        errors.append("payoff is clichéd")
    title = select_title(story)
    if len(title) > 70:
        errors.append("title exceeds 70 characters")
    if not story_id:
        errors.append("id is empty")
    return errors


def load_stories(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StoryError(f"Story catalog is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StoryError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise StoryError("Story catalog must be a non-empty JSON array")
    stories: list[dict[str, Any]] = []
    ids: set[str] = set()
    selected_hooks: set[str] = set()
    selected_titles: set[str] = set()
    for index, item in enumerate(payload):
        story = normalize_story(item, index)
        errors = validate_story(story)
        if errors:
            raise StoryError(f"Story {story.get('id', index)} failed quality checks: {'; '.join(errors)}")
        if story["id"] in ids:
            raise StoryError(f"Duplicate story id: {story['id']}")
        hook = select_hook(story).casefold()
        title = select_title(story).casefold()
        if hook in selected_hooks:
            raise StoryError(f"Duplicate selected hook: {hook}")
        if title in selected_titles:
            raise StoryError(f"Duplicate selected title: {title}")
        ids.add(story["id"])
        selected_hooks.add(hook)
        selected_titles.add(title)
        stories.append(story)
    similarity_cache = [(story["id"], similarity_terms(story_script(story))) for story in stories]
    for index, (story_id, terms) in enumerate(similarity_cache):
        for other_id, other_terms in similarity_cache[:index]:
            similarity = jaccard_similarity(terms, other_terms)
            if similarity >= 0.88:
                raise StoryError(
                    f"Stories {other_id} and {story_id} are too similar ({similarity:.2f})"
                )
    return stories


def similarity_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9$]+", text.casefold())
        if len(token) > 2 and token not in STOP_WORDS
    }


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def recent_similarity(story: dict[str, Any], history: list[dict[str, Any]]) -> float:
    terms = similarity_terms(story_script(story))
    similarities = []
    for event in history[-RECENT_WINDOW:]:
        recent_terms = {clean_text(value).casefold() for value in event.get("similarity_terms", [])}
        similarities.append(jaccard_similarity(terms, recent_terms))
    return max(similarities, default=0.0)


def select_story(
    stories: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    rng: random.Random | random.SystemRandom | None = None,
) -> dict[str, Any]:
    if not stories:
        raise StoryError("The micro-story catalog is empty")
    chooser = rng or random.SystemRandom()
    used = set(state.get("used_ids", []))
    history = [event for event in state.get("history", []) if isinstance(event, dict)]
    candidates = [story for story in stories if story["id"] not in used]
    candidates = [story for story in candidates if recent_similarity(story, history) < SIMILARITY_LIMIT]
    if not candidates:
        raise StoryError("No distinct unused micro-story remains; curate and refill the story catalog")
    recent = history[-8:]
    recent_pillars = [clean_text(event.get("pillar", "")) for event in recent]
    recent_topics = [clean_text(event.get("topic", "")) for event in recent]
    recent_perspectives = [clean_text(event.get("perspective", "")) for event in recent]

    def freshness(story: dict[str, Any]) -> float:
        score = 0.0
        score += 5.0 if story["pillar"] not in recent_pillars[-3:] else 0.0
        score += 3.0 if story["topic"] not in recent_topics[-6:] else 0.0
        score += 2.0 if story["perspective"] not in recent_perspectives[-3:] else 0.0
        score += hook_score(select_hook(story)) * 0.2
        score -= recent_similarity(story, history) * 8.0
        return score

    ranked = sorted(candidates, key=freshness, reverse=True)
    top_score = freshness(ranked[0])
    top = [story for story in ranked if freshness(story) >= top_score - 1.5][:8]
    return chooser.choice(top)


def story_history_event(story: dict[str, Any], hook: str, title: str) -> dict[str, Any]:
    return {
        "id": story["id"],
        "used_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pillar": story["pillar"],
        "topic": story["topic"],
        "theme": story["theme"],
        "perspective": story["perspective"],
        "hook_type": story["hook_type"],
        "hook": hook,
        "title": title,
        "ending_concept": story["ending_concept"],
        "key_phrases": story["key_phrases"],
        "similarity_terms": sorted(similarity_terms(story_script(story, hook))),
    }
