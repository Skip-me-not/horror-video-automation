from __future__ import annotations

import re


class MetadataGenerator:
    def generate(self, script: dict[str, object]) -> dict[str, object]:
        title = re.sub(r"\s+", " ", str(script["title"])).strip().rstrip(".!?")
        if len(title) > 88:
            title = title[:85].rsplit(" ", 1)[0] + "…"
        record_word = "archive" if str(script["evidence_type"]) != "reference_summary" else "reference article"
        description = (
            f"A documented horror fact from {script['source_institution']}.\n"
            f"Evidence label: {str(script['evidence_type']).replace('_', ' ')}.\n"
            f"The {record_word} documents this account, subject, or tradition; it does not prove a supernatural explanation.\n\n"
            f"Source: {script['source_url']}\n"
            f"Rights: {script['source_rights']}"
        )
        evidence_tag = "#oralhistory" if script["evidence_type"] == "oral_history" else "#folklore"
        return {"title": title, "description": description, "hashtags": ["#horrorfacts", evidence_tag, "#shorts"]}

    @staticmethod
    def validate(metadata: dict[str, object]) -> list[str]:
        errors: list[str] = []
        if not str(metadata.get("title", "")).strip() or len(str(metadata.get("title", ""))) > 100:
            errors.append("title must contain 1-100 characters")
        if not str(metadata.get("description", "")).strip():
            errors.append("description is required")
        tags = metadata.get("hashtags")
        if not isinstance(tags, list) or not 1 <= len(tags) <= 5 or any(not str(tag).startswith("#") for tag in tags):
            errors.append("hashtags must contain 1-5 hashtag values")
        if "true story" in str(metadata.get("title", "")).casefold():
            errors.append("unsupported TRUE STORY claim")
        if "Source: https://" not in str(metadata.get("description", "")):
            errors.append("description must include a direct source link")
        return errors
