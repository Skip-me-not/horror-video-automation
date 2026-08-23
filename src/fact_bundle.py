from __future__ import annotations

import re
from typing import Iterable


NUMBER_WORDS = ("one", "two", "three", "four", "five")


def _clean_summary(script: dict[str, object]) -> str:
    text = str(script.get("script", "")).strip()
    marker = "The source overview begins by describing it this way:"
    if marker in text:
        text = text.split(marker, 1)[1].split(". It is grouped with", 1)[0]
    else:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        text = sentences[1] if len(sentences) > 1 else sentences[0]
    text = re.split(r"(?<=[.!?])\s+", text)[0]
    text = re.sub(r"\([^)]{0,120}\)", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -:;,.")
    # The bank stores a deliberately short source excerpt. Remove a trailing
    # cut-off clause instead of reading an obviously unfinished sentence.
    text = re.split(r",\s+(?:a town\b|is an?\b)", text, maxsplit=1, flags=re.IGNORECASE)[0]
    words = text.split()
    if len(words) > 20:
        comma_positions = [index for index, word in enumerate(words) if word.endswith(",")]
        useful = [index for index in comma_positions if index >= 7]
        if useful:
            words = words[: useful[-1] + 1]
        else:
            words = words[:20]
        text = " ".join(words).rstrip(" ,;:")
    dangling = {"a", "an", "and", "or", "of", "to", "with", "who", "whose", "natural"}
    if text.split()[-1].casefold().strip(",;:") in dangling:
        title = str(script.get("source_title", "This subject")).strip()
        category = str(script.get("category", "horror folklore")).casefold()
        text = f"Sources document {title} within {category} traditions and reported beliefs"
    return text.rstrip(".!?") + "."


def fact_line(script: dict[str, object], number: int) -> str:
    label = NUMBER_WORDS[number - 1] if 1 <= number <= len(NUMBER_WORDS) else str(number)
    return f"Fact {label}. {_clean_summary(script)}"


def build_narration(scripts: Iterable[dict[str, object]]) -> str:
    items = list(scripts)
    count = len(items)
    intro = f"{count} horror facts you weren't supposed to know."
    facts = [fact_line(item, index) for index, item in enumerate(items, 1)]
    return " ".join([intro, *facts, "Follow for more documented horror facts."])
