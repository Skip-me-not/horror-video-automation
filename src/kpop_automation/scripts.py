from __future__ import annotations

import hashlib
import re
from typing import Any

from .models import Topic


STRUCTURES = {
    "idol_storytelling": ("Here is a documented chapter in {entity}'s journey.", "The public record gives this context:", "That makes this moment part of a larger career story."),
    "viral_moments": ("This {entity} moment spread fast, but here is the verified context.", "Published coverage describes it this way:", "The documented detail—not speculation—is what made it notable."),
    "fan_debate": ("Fans can reasonably disagree about this {entity} topic.", "The facts everyone starts with are:", "Which interpretation fits the documented context best?"),
    "transformation": ("This is one documented step in {entity}'s artistic evolution.", "The dated record shows:", "It is a useful marker of how the work developed."),
    "funny_relatable": ("A documented {entity} story became unexpectedly relatable.", "The published account says:", "The context is simple, public, and fun without inventing anything private."),
    "trending_news": ("Here is the verified {entity} update in under a minute.", "The announcement and coverage confirm:", "Check the cited sources for updates as the story develops."),
    "idol_interactions": ("This documented {entity} interaction has a clear public backstory.", "Reliable sources describe:", "It is worth enjoying without turning it into a private-life rumor."),
    "explained_analysis": ("Here is what the documented context adds to this {entity} moment.", "Start with the confirmed details:", "That evidence supports the interpretation without overstating it."),
}

FACT_LEADS = (
    "One documented detail:",
    "The cited report also records:",
    "Another confirmed point:",
    "The published account further states:",
)


def _sentence(value: str, words: int = 38) -> str:
    value = re.sub(r"https?://\S+|\s+", " ", value).strip(" -—:;,.!")
    first = re.split(r"(?<=[.!?])\s+", value, maxsplit=1)[0]
    clipped = " ".join(first.split()[:words])
    return clipped.rstrip(" ,;:.!?") + "."


def generate_script(topic: Topic, target_words: int = 135) -> dict[str, Any]:
    hook, context, ending = STRUCTURES[topic.category]
    seed = int(hashlib.sha256(topic.topic_id.encode()).hexdigest()[:8], 16)
    claims = list(topic.claims)
    if not claims:
        raise ValueError("topic has no source-grounded claims")
    chosen = claims[seed % len(claims):] + claims[:seed % len(claims)]
    source_names = list(dict.fromkeys(source.publisher for source in topic.sources))
    parts = [hook.format(entity=topic.entity), context]
    for index, claim in enumerate(chosen):
        parts.append(f"{FACT_LEADS[index % len(FACT_LEADS)]} {_sentence(claim)}")
    parts.append(f"This summary is based on {', '.join(source_names[:2])}.")
    parts.append(ending.format(entity=topic.entity))
    while len(" ".join(parts).split()) > target_words and len(parts) > 4:
        parts.pop(-3)
    narration = " ".join(parts)
    hook_text = hook.format(entity=topic.entity)
    headline = topic.title.strip().rstrip(".!?")
    title_options = list(dict.fromkeys([
        headline[:69],
        f"What Happened With {topic.entity}?"[:69],
        f"{topic.entity}: The Verified Update"[:69],
        f"The Latest Confirmed {topic.entity} News"[:69],
        f"Why {topic.entity} Is in the News"[:69],
    ]))
    title = title_options[0]
    description = (
        f"{headline}. This original Lululala update summarizes confirmed public reporting.\n\n"
        + "\n".join(f"Source: {source.publisher} — {source.url}" for source in topic.sources)
        + "\n\n#KoreanCelebrity #KDrama #KoreanEntertainment #Shorts"
    )
    return {
        "hook": hook_text, "narration": narration, "word_count": len(narration.split()),
        "generation_mode": "deterministic_source_summary",
        "title": title, "title_options": title_options, "description": description,
        "tags": ["Lululala", "KoreanCelebrity", "KDrama", "Kpop", topic.entity, "shorts"],
        "source_ids": [source.source_id for source in topic.sources],
        "claim_fingerprints": [hashlib.sha256(claim.encode()).hexdigest() for claim in chosen],
    }


def publication_script_errors(topic: Topic, script: dict[str, Any]) -> list[str]:
    """Conservative checks for a no-API script before public upload."""
    errors: list[str] = []
    narration = str(script.get("narration", ""))
    if not 120 <= len(narration.split()) <= 150:
        errors.append("narration needs 120–150 verified words")
    if topic.entity.casefold() not in narration.casefold():
        errors.append("narration omits the subject")
    spoken = re.findall(r"[a-z0-9]+", narration.casefold())
    spoken_shingles = {tuple(spoken[index:index + 8]) for index in range(max(0, len(spoken) - 7))}
    evidence = " ".join(source.title + " " + source.evidence for source in topic.sources)
    evidence_numbers = set(re.findall(r"\b\d+\b", evidence))
    if set(re.findall(r"\b\d+\b", narration)) - evidence_numbers:
        errors.append("narration introduces a number absent from its sources")
    for source in topic.sources:
        for source_text in (source.title, source.evidence):
            words = re.findall(r"[a-z0-9]+", source_text.casefold())
            if any(tuple(words[index:index + 8]) in spoken_shingles
                   for index in range(max(0, len(words) - 7))):
                errors.append("narration copies eight consecutive source words")
                return errors
    return errors
