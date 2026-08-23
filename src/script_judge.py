from __future__ import annotations

import re
from dataclasses import dataclass


FORBIDDEN_OPENINGS = (
    "once upon a time", "it was a dark and stormy night",
    "let me tell you a scary story", "hello", "welcome to",
)


@dataclass(frozen=True)
class QualityResult:
    hook: int
    curiosity: int
    escalation: int
    visual_potential: int
    twist_payoff: int
    reasons: tuple[str, ...]

    @property
    def total(self) -> int:
        return self.hook + self.curiosity + self.escalation + self.visual_potential + self.twist_payoff


class ScriptJudge:
    def score(self, candidate: dict[str, object]) -> QualityResult:
        if candidate.get("content_type") == "sourced_horror_fact":
            return self._score_fact(candidate)
        script = str(candidate.get("script", "")).strip()
        hook_text = str(candidate.get("hook", "")).strip()
        words = re.findall(r"\b[\w'’-]+\b", script)
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", script) if part.strip()]
        reasons: list[str] = []
        bad_opening = script.casefold().startswith(FORBIDDEN_OPENINGS)
        hook = 9 if hook_text and len(hook_text.split()) <= 28 and not bad_opening else (8 if hook_text and not bad_opening else 5)
        if bad_opening:
            reasons.append("generic opening")
        unanswered = any(token in hook_text.casefold() for token in ("but", "not", "tomorrow", "behind", "twice", "never"))
        curiosity = 9 if unanswered else 8
        escalation_terms = sum(script.casefold().count(term) for term in ("then", "closer", "behind", "each", "last", "inside", "follow"))
        escalation = min(10, 8 + min(2, escalation_terms))
        visual_terms = sum(script.casefold().count(term) for term in ("camera", "light", "screen", "door", "shadow", "glass", "hallway", "phone", "figure"))
        visual = min(10, 8 + min(2, visual_terms // 2))
        ending = sentences[-1].casefold() if sentences else ""
        twist = 9 if len(sentences) >= 4 and any(term in ending for term in ("me", "inside", "behind", "voice", "opened", "shadow", "death")) else 7
        if not 60 <= len(words) <= 100:
            reasons.append(f"word count {len(words)} outside 60-100")
            hook = max(0, hook - 2)
            curiosity = max(0, curiosity - 1)
        if len(sentences) < 4:
            reasons.append("too few beats")
            escalation = max(0, escalation - 3)
        return QualityResult(hook, curiosity, escalation, visual, twist, tuple(reasons))

    @staticmethod
    def _score_fact(candidate: dict[str, object]) -> QualityResult:
        script = str(candidate.get("script", "")).strip()
        hook_text = str(candidate.get("hook", "")).strip()
        words = re.findall(r"\b[\w'’-]+\b", script)
        reasons: list[str] = []
        hook = 9 if 6 <= len(hook_text.split()) <= 32 else 7
        specificity = sum(bool(candidate.get(field)) for field in ("source_date", "location", "source_title", "source_institution"))
        curiosity = 8 + min(2, specificity // 2)
        evidence = 10 if str(candidate.get("source_url", "")).startswith("https://") else 5
        visual = 9 if candidate.get("location") and candidate.get("source_date") else 7
        caveat_terms = ("does not prove", "not verified", "not scientifically confirmed", "not paranormal proof")
        caveat = 10 if any(term in script.casefold() for term in caveat_terms) else 5
        if not 60 <= len(words) <= 100:
            reasons.append(f"word count {len(words)} outside 60-100")
            hook = max(0, hook - 2)
        if evidence < 10:
            reasons.append("missing direct source URL")
        if caveat < 10:
            reasons.append("missing evidence caveat")
        return QualityResult(hook, curiosity, evidence, visual, caveat, tuple(reasons))
