from __future__ import annotations

import re

from .fact_source_provider import FactSource


def _clean(value: str) -> str:
    return " ".join(value.replace("\n", " ").split()).strip(" ,.;")


def _short(value: str, words: int) -> str:
    parts = _clean(value).split()
    return " ".join(parts[:words])


def _year(value: str) -> str:
    match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", value)
    return match.group(1) if match else "an undated period"


def _speaker(source: FactSource) -> str:
    if not source.contributors:
        return "a named or unidentified contributor"
    return _short(source.contributors[-1], 7)


class FactScriptGenerator:
    """Turns verifiable archive metadata into short scripts without inventing events."""

    def generate(self, source: FactSource, index: int) -> dict[str, object]:
        year = _year(source.source_date)
        location = _short(source.location, 10) or "a location recorded by the archive"
        speaker = _speaker(source)
        collection = _short(source.source_collection, 15)
        subjects = ", ".join(_short(value, 5) for value in source.subjects[:3]) or "supernatural belief and narrative tradition"
        format_name = _short(source.original_format[0], 5) if source.original_format else "archival item"
        title = _clean(source.source_title)
        spoken_title = _short(title, 12)
        hooks = [
            f"Here is a horror fact most people do not know: an archive preserves {spoken_title!r} from {year}.",
            f"This is not an invented ghost story; {spoken_title!r} is a real cataloged archive item.",
            f"A disturbing piece of folklore was formally preserved under the title {spoken_title!r}.",
            f"In {year}, an account now cataloged as {spoken_title!r} entered the historical record.",
            f"The eerie fact is not whether a ghost existed, but that {spoken_title!r} was actually documented.",
        ]
        hook = hooks[index % len(hooks)]
        if source.evidence_type == "reference_summary":
            summary = _short(source.notes[0], 20) if source.notes else "The subject is documented as a horror or supernatural tradition"
            hook = [
                f"Here is a horror fact most people do not know: {spoken_title!r} has a documented cultural record.",
                f"This eerie belief is documented, even if the supernatural claim is not: {spoken_title!r}.",
                f"The unsettling fact behind {spoken_title!r} is preserved in a cited reference article.",
            ][index % 3]
            body = (
                f"The source overview begins by describing it this way: {summary}. It is grouped with {subjects} and the article provides references for deeper checking. "
                "This verifies that the subject, tradition, or report is documented; it does not prove a paranormal explanation. The direct article link and reuse license are in the description."
            )
            script = f"{hook} {body}"
        else:
            script = ""
        bodies = [
            f"The Library of Congress lists it as a {format_name}, connected to {speaker}, and places it in {location}. Its catalog subjects include {subjects}. It belongs to the {collection} collection. The archive proves that this account or belief was recorded; it does not prove a supernatural explanation. The item page and rights note are linked in the description.",
            f"The record dates to {year} and identifies {location}. It credits {speaker} and connects the item with {subjects}. The source collection is {collection}. That makes the documentation real, while the ghostly claim remains a reported experience or piece of folklore—not a scientifically confirmed event. You can inspect the original catalog record through the source link.",
            f"According to its catalog metadata, the item is associated with {speaker} in {location}. The archive classifies it with {subjects} and preserves it in {collection}. What is verified is the existence and provenance of the record. What is not verified is any supernatural interpretation. That distinction is why this is labeled {source.evidence_type.replace('_', ' ')}, not paranormal proof.",
            f"The catalog dates the item to {year}, identifies {speaker}, and ties it to {location}. It is preserved through {collection}, with subjects including {subjects}. This is a documented trace of what people told, performed, remembered, or believed. The archive does not certify that a ghost was real; it certifies that the account itself entered the historical record.",
        ]
        if not script:
            script = f"{hook} {bodies[index % len(bodies)]}"
        words = re.findall(r"\b[\w'’-]+\b", script)
        if len(words) > 100:
            script = script.replace(" The item page and rights note are linked in the description.", "")
            script = script.replace(" You can inspect the original catalog record through the source link.", "")
            words = re.findall(r"\b[\w'’-]+\b", script)
        if len(words) < 60:
            script += " The source date, collection, evidence label, and direct archive link are included for independent checking."
            words = re.findall(r"\b[\w'’-]+\b", script)
        display_title = self._display_title(source, year, location, speaker)
        return {
            "content_type": "sourced_horror_fact",
            "evidence_type": source.evidence_type,
            "category": self._category(source),
            "location": location,
            "source_id": source.source_id,
            "source_title": title,
            "source_url": source.source_url,
            "source_institution": source.source_institution,
            "source_date": source.source_date,
            "source_collection": source.source_collection,
            "source_rights": source.source_rights,
            "source_contributors": list(source.contributors),
            "source_subjects": list(source.subjects),
            "source_notes": list(source.notes),
            "verification_note": "The archival record is verified. Any supernatural interpretation remains an attributed report, belief, performance, or folklore claim.",
            "plot_fingerprint": f"source|{source.source_id.casefold()}",
            "title": display_title,
            "hook": hook,
            "script": script,
            "word_count": len(words),
            "estimated_duration": round(len(words) / 2.65, 1),
        }

    @staticmethod
    def _category(source: FactSource) -> str:
        subjects = " ".join(source.subjects).casefold()
        if "witch" in subjects:
            return "Witchcraft Record"
        if "ghost" in subjects:
            return "Ghost Oral History" if source.evidence_type == "oral_history" else "Ghost Folklore Record"
        if "death" in subjects or "burial" in subjects:
            return "Death and Burial Lore"
        if any(term in subjects for term in ("devil", "demon", "possession", "exorcism")):
            return "Demon and Devil Lore"
        if any(term in subjects for term in ("monster", "vampire", "werewolf", "shapeshift")):
            return "Monster and Shapeshifter Lore"
        if any(term in subjects for term in ("omen", "superstition", "evil eye")):
            return "Omens and Superstitions"
        if any(term in subjects for term in ("legend", "folklore", "myth", "creature")):
            return "Myth and Creature Lore"
        if source.evidence_type == "oral_history":
            return "Reported Experience"
        if source.evidence_type == "reference_summary":
            return "Documented Horror Reference"
        return "Archival Horror Fact"

    @staticmethod
    def _display_title(source: FactSource, year: str, location: str, speaker: str) -> str:
        base = _clean(source.source_title)
        if source.evidence_type == "reference_summary":
            choices = (
                f"Horror Fact: {base}",
                f"The Dark Folklore Behind {base}",
                f"{base}: What the Sources Actually Say",
                f"The Documented Mystery of {base}",
            )
            return choices[sum(source.source_id.encode("utf-8")) % len(choices)][:96]
        choices = (
            f"The Archived Horror Record from {year}",
            f"Why {base} Is in a National Archive",
            f"The {year} Account Preserved from {location}",
            f"The Archive Record Connected to {speaker}",
        )
        return choices[sum(source.source_id.encode("utf-8")) % len(choices)][:96]
