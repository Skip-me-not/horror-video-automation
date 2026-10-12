#!/usr/bin/env python3
"""Build source-grounded spoken commentary without an AI or external model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class EditorialScriptError(RuntimeError):
    """The deterministic script could not satisfy the Shorts contract."""


@dataclass(frozen=True)
class ScriptResult:
    segments: list[dict[str, Any]]
    engine: str = "editorial_deterministic"
    model: str = "none"
    prompt_version: str = "none"

    @property
    def narration(self) -> str:
        return " ".join(segment["text"] for segment in self.segments)


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def generate_editorial_script(idol: str, facts: list[dict[str, Any]]) -> ScriptResult:
    if len(facts) not in {3, 4}:
        raise EditorialScriptError("A Short needs exactly 3 or 4 source items")
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
        if not title or not subreddit:
            raise EditorialScriptError("A source item is missing its title or subreddit")
        segments.append(
            {
                "kind": "fact",
                "fact_number": index,
                "text": (
                    f"Point {index}: the discussion focused on {title}. It reached {score} upvotes "
                    f"and {comments} comments in r slash {subreddit}, showing why fans kept debating it."
                ),
            }
        )
    segments.append(
        {
            "kind": "outro",
            "text": f"That is the source discussion, not a verified biography. Follow for another {idol} story and comment the detail we should check next.",
        }
    )
    total = sum(word_count(segment["text"]) for segment in segments)
    if not 95 <= total <= 180:
        raise EditorialScriptError(f"Generated script has {total} words; expected 95–180")
    return ScriptResult(segments=segments)
