from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


CATEGORIES = (
    "idol_storytelling", "viral_moments", "fan_debate", "transformation",
    "funny_relatable", "trending_news", "idol_interactions", "explained_analysis",
)


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    title: str
    url: str
    publisher: str
    published_at: str
    accessed_at: str
    evidence: str
    entities: tuple[str, ...]
    category: str
    reliability: int
    source_kind: str
    rights: str = "facts_only"
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["entities"] = list(self.entities)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceRecord":
        return cls(**{**value, "entities": tuple(value.get("entities", []))})


@dataclass(frozen=True)
class Topic:
    topic_id: str
    title: str
    category: str
    entity: str
    sources: tuple[SourceRecord, ...]
    claims: tuple[str, ...]
    review_reason: str = ""
    score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id, "title": self.title, "category": self.category,
            "entity": self.entity, "sources": [item.to_dict() for item in self.sources],
            "claims": list(self.claims), "review_reason": self.review_reason, "score": self.score,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Topic":
        return cls(
            topic_id=value["topic_id"], title=value["title"], category=value["category"],
            entity=value["entity"], sources=tuple(SourceRecord.from_dict(x) for x in value["sources"]),
            claims=tuple(value["claims"]), review_reason=value.get("review_reason", ""),
            score=int(value.get("score", 0)),
        )


@dataclass
class ProductionManifest:
    content_id: str
    slot_id: str
    created_at: str
    status: str
    topic: dict[str, Any]
    script: dict[str, Any]
    assets: list[dict[str, Any]] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)
    upload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
