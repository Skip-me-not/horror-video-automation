#!/usr/bin/env python3
"""Low-usage AI packaging optimizer for the K-pop ranked Short."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import requests


DEFAULT_ENDPOINT = "https://models.github.ai/inference/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
PROMPT_VERSION = "kpop-packaging-v1"


class AIOptimizationError(RuntimeError):
    """The model response did not satisfy the safe packaging contract."""


@dataclass(frozen=True)
class OptimizationResult:
    title: str
    hook: str
    subtitle: str
    cta: str
    engine: str
    model: str
    prompt_version: str = PROMPT_VERSION

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def word_count(value: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", value))


def source_packet(stories: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    packet = []
    for story in stories:
        packet.append({
            "story_id": clean_text(story.get("story_id")),
            "idol": clean_text(story.get("ranked_topic")),
            "headline": clean_text(story.get("headline")),
            "subreddit": clean_text(story.get("source_name")),
            "reddit_score": max(0, int(story.get("reddit_score") or 0)),
            "reddit_comments": max(0, int(story.get("reddit_comments") or 0)),
            "date": clean_text(story.get("date")),
        })
    return packet


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _content_from_response(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AIOptimizationError("AI response has no choices")
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(
            str(item.get("text", "")) for item in content if isinstance(item, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise AIOptimizationError("AI response has no text content")
    return _strip_json_fence(content)


def _fallback(topic: str) -> OptimizationResult:
    topic = clean_text(topic) or "K-pop"
    return OptimizationResult(
        title=f"6 {topic} Moments Fans Ranked Highest",
        hook="WAIT FOR #1",
        subtitle=f"FANS RANKED THESE {topic.upper()} MOMENTS",
        cta="WHO SHOULD WE RANK NEXT?",
        engine="deterministic_fallback",
        model="none",
    )


def validate_optimization(payload: Any, topic: str) -> OptimizationResult:
    if not isinstance(payload, dict):
        raise AIOptimizationError("AI optimization must be a JSON object")
    title = clean_text(payload.get("title"))
    hook = clean_text(payload.get("hook"))
    subtitle = clean_text(payload.get("subtitle"))
    cta = clean_text(payload.get("cta"))
    if not 20 <= len(title) <= 100:
        raise AIOptimizationError("AI title must be between 20 and 100 characters")
    if not 3 <= word_count(hook) <= 14:
        raise AIOptimizationError("AI hook is outside the safe word range")
    if not 3 <= word_count(subtitle) <= 16:
        raise AIOptimizationError("AI subtitle is outside the safe word range")
    if not 4 <= word_count(cta) <= 16:
        raise AIOptimizationError("AI CTA is outside the safe word range")
    if "#" in title or "http" in title.casefold() or "http" in hook.casefold():
        raise AIOptimizationError("AI packaging contains a hashtag or URL in a title/hook")
    if clean_text(topic).casefold() not in " ".join((title, hook, subtitle)).casefold():
        raise AIOptimizationError("AI packaging does not mention the selected topic")
    return OptimizationResult(
        title=title[:100],
        hook=hook,
        subtitle=subtitle,
        cta=cta,
        engine="github_models",
        model=DEFAULT_MODEL,
    )


def optimize_packaging(
    stories: list[dict[str, Any]],
    *,
    token: str = "",
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = DEFAULT_MODEL,
    mode: str = "auto",
    session: requests.Session | None = None,
) -> OptimizationResult:
    if len(stories) != 6:
        raise AIOptimizationError("AI packaging requires exactly six stories")
    if mode not in {"auto", "off", "required"}:
        raise AIOptimizationError(f"Unsupported AI mode: {mode}")
    topic = clean_text(stories[0].get("ranked_topic")) or "K-pop"
    if mode == "off" or not token:
        if mode == "required" and not token:
            raise AIOptimizationError("AI mode is required but no model token is available")
        return _fallback(topic)

    source_json = json.dumps(source_packet(stories), ensure_ascii=False)
    system = (
        "You are a careful YouTube Shorts packaging editor. Return JSON only. "
        "Use only the supplied source signals. Do not invent achievements, quotes, dates, "
        "or claims. Create curiosity without fake urgency, harassment, rumors, or emojis."
    )
    user = f"""Create packaging for one original 35-second K-pop countdown about {topic}.
The video contains six public fan-discussion clips, ranked by their supplied Reddit signals.
Return exactly this JSON shape:
{{"title":"...","hook":"...","subtitle":"...","cta":"..."}}
Rules:
- title: 35-90 characters, mention {topic}, specific and distinct from generic '6 moments fans ranked highest'
- hook: 3-12 spoken words for the first 1.8 seconds; mention {topic} or the ranking
- subtitle: 4-14 words for an on-screen context line
- cta: 4-14 words, ask one concrete comment question
- never invent a fact or use a URL, hashtag, emoji, rumor, or unsupported superlative
Source signals:
{source_json}"""
    client = session or requests.Session()
    try:
        response = client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.35,
                "max_tokens": 220,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=(10, 45),
        )
        response.raise_for_status()
        result = validate_optimization(json.loads(_content_from_response(response.json())), topic)
        return OptimizationResult(
            title=result.title,
            hook=result.hook,
            subtitle=result.subtitle,
            cta=result.cta,
            engine="github_models",
            model=model,
        )
    except (requests.RequestException, TimeoutError, ValueError, TypeError, AIOptimizationError) as exc:
        if mode == "required":
            raise AIOptimizationError(f"AI packaging failed: {exc}") from exc
        print(f"WARNING: AI packaging unavailable; using deterministic fallback: {exc}")
        return _fallback(topic)
