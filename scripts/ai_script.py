#!/usr/bin/env python3
"""Turn Reddit source signals into an original, structured Shorts script."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable

import requests


DEFAULT_ENDPOINT = "https://models.github.ai/inference/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"


class AIScriptError(RuntimeError):
    """The AI response was unavailable or failed the Shorts script contract."""


@dataclass(frozen=True)
class ScriptResult:
    segments: list[dict[str, Any]]
    engine: str
    model: str
    prompt_version: str = "idol-short-v1"

    @property
    def narration(self) -> str:
        return " ".join(segment["text"] for segment in self.segments)


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def source_packet(facts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": str(fact.get("id", "")),
            "title": clean_text(fact.get("title")),
            "subreddit": clean_text(fact.get("subreddit")),
            "score": int(fact.get("score") or 0),
            "comments": int(fact.get("num_comments") or 0),
        }
        for fact in facts
    ]


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _content_from_response(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AIScriptError("AI response has no choices")
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    if not isinstance(content, str) or not content.strip():
        raise AIScriptError("AI response has no text content")
    return _strip_json_fence(content)


def validate_script(payload: Any, idol: str, fact_count: int) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise AIScriptError("AI script must be a JSON object")
    hook = clean_text(payload.get("hook"))
    facts = payload.get("facts")
    outro = clean_text(payload.get("outro"))
    if not isinstance(facts, list) or len(facts) != fact_count:
        raise AIScriptError(f"AI script must contain exactly {fact_count} fact beats")
    if not hook or not outro:
        raise AIScriptError("AI script must contain hook and outro")
    if not 8 <= word_count(hook) <= 24:
        raise AIScriptError("AI hook is outside the safe word range")
    if not 14 <= word_count(outro) <= 28:
        raise AIScriptError("AI outro is outside the safe word range")

    segments: list[dict[str, Any]] = [{"kind": "hook", "text": hook}]
    for index, item in enumerate(facts, start=1):
        if not isinstance(item, dict):
            raise AIScriptError("AI fact beat must be an object")
        text = clean_text(item.get("text"))
        if not 17 <= word_count(text) <= 42:
            raise AIScriptError(f"AI fact {index} is outside the safe word range")
        segments.append({"kind": "fact", "fact_number": index, "text": text})
    segments.append({"kind": "outro", "text": outro})
    total = sum(word_count(segment["text"]) for segment in segments)
    if not 95 <= total <= 180:
        raise AIScriptError(f"AI script has {total} words; expected 95–180")
    if idol.casefold() not in " ".join(segment["text"] for segment in segments).casefold():
        raise AIScriptError("AI script does not mention the selected idol")
    return segments


def _fallback_script(idol: str, facts: list[dict[str, Any]]) -> ScriptResult:
    """Editorial fallback: reorganize source signals without pretending they are verified facts."""
    segments: list[dict[str, Any]] = [
        {
            "kind": "hook",
            "text": f"{len(facts)} details about {idol} that turned a K-pop discussion into a full conversation.",
        }
    ]
    for index, fact in enumerate(facts, start=1):
        title = clean_text(fact.get("title"))
        subreddit = clean_text(fact.get("subreddit"))
        score = int(fact.get("score") or 0)
        comments = int(fact.get("num_comments") or 0)
        segments.append(
            {
                "kind": "fact",
                "fact_number": index,
                "text": (
                    f"Point {index}: the discussion focused on {title}. It reached {score} upvotes "
                    f"and {comments} comments in r slash {subreddit}, showing exactly why fans kept debating it."
                ),
            }
        )
    segments.append(
        {
            "kind": "outro",
            "text": f"That is the Reddit conversation, not a verified biography. Follow for another {idol} story and comment the detail we should check next.",
        }
    )
    return ScriptResult(segments=segments, engine="editorial_fallback", model="none")


def generate_script(
    idol: str,
    facts: list[dict[str, Any]],
    *,
    token: str = "",
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = DEFAULT_MODEL,
    mode: str = "auto",
    session: requests.Session | None = None,
) -> ScriptResult:
    if len(facts) not in {3, 4}:
        raise AIScriptError("AI script generation requires 3 or 4 source items")
    if mode not in {"auto", "required", "fallback"}:
        raise AIScriptError(f"Unsupported AI script mode: {mode}")
    if mode == "fallback" or not token:
        if mode == "required" and not token:
            raise AIScriptError("AI_SCRIPT_MODE=required but no model token is available")
        return _fallback_script(idol, facts)

    client = session or requests.Session()
    sources = json.dumps(source_packet(facts), ensure_ascii=False)
    system = (
        "You are an editorial short-video writer. Return JSON only. Never invent a fact, date, "
        "number, quote, or achievement. The Reddit titles are source signals, not proof; preserve "
        "uncertainty with wording like 'the discussion focused on' when needed. Write natural spoken English."
    )
    user = f"""Create a 55–65 second vertical Short script about {idol}.
Use exactly {len(facts)} source items and rewrite them into original commentary instead of reading Reddit titles aloud.
Structure:
- hook: 8–18 words, an open loop
- facts: exactly {len(facts)} objects, each text 17–40 words, numbered naturally in the sentence
- outro: 14–26 words, a concise comment/follow CTA
Total: 105–165 words.
Avoid: 'Redditors pushed', fake certainty, generic 'you won't believe', clickbait, emojis, and legal/copyright claims.
Return this exact JSON shape: {{"hook":"...","facts":[{{"text":"..."}}],"outro":"..."}}
Source signals:
{sources}"""
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
                "temperature": 0.55,
                "max_tokens": 500,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=(10, 75),
        )
        response.raise_for_status()
        payload = response.json()
        content = _content_from_response(payload)
        segments = validate_script(json.loads(content), idol, len(facts))
        return ScriptResult(segments=segments, engine="github_models", model=model)
    except (requests.RequestException, TimeoutError, ValueError, TypeError, AIScriptError) as exc:
        if mode == "required":
            raise AIScriptError(f"AI script generation failed: {exc}") from exc
        return _fallback_script(idol, facts)
