from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.kpop_automation.assets import load_approved_assets
from src.kpop_automation.config import load_config
from src.kpop_automation.models import SourceRecord, Topic
from src.kpop_automation.pipeline import produce
from src.kpop_automation.research import canonical_url, parse_feed
from src.kpop_automation.scripts import STRUCTURES, generate_script
from src.kpop_automation.state import finalize_upload, queue_manifest
from src.kpop_automation.topics import rank_topics


def test_config_has_eight_weighted_categories(repo_root: Path):
    config = load_config(repo_root / "config" / "kpop.yaml")
    assert len(config["content"]["category_weights"]) == 8
    assert sum(config["content"]["category_weights"].values()) == pytest.approx(1.0)
    assert config["channel"]["auto_publish"] is True
    assert config["channel"]["upload_privacy"] == "public"
    assert config["schedule"]["slots"] == ["07:00", "12:00", "15:00", "19:00"]


def test_feed_parser_extracts_grounded_entity_and_canonical_url():
    payload = b'''<?xml version="1.0"?><rss><channel><item>
      <title>BTS announces a documented album release</title>
      <link>https://agency.example/news/bts-release?utm_source=x</link>
      <description>The official notice confirms the release date.</description>
      <pubDate>Tue, 22 Sep 2026 10:00:00 GMT</pubDate>
    </item></channel></rss>'''
    source = {"name": "Official Agency", "kind": "official", "reliability": 3, "rights": "facts_only"}
    records = parse_feed(payload, source, ["BTS"], "2026-09-23T00:00:00+00:00")
    assert len(records) == 1
    assert records[0].entities == ("BTS",)
    assert records[0].url == "https://agency.example/news/bts-release"
    assert canonical_url("HTTPS://Agency.Example/news/") == "https://agency.example/news"


def _source(identifier: str, publisher: str = "Official", kind: str = "official") -> SourceRecord:
    return SourceRecord(identifier, "IVE announces a release", f"https://{publisher.lower()}.example/{identifier}",
                        publisher, "2026-09-22T00:00:00+00:00", "2026-09-23T00:00:00+00:00",
                        "The notice confirms a release date.", ("IVE",), "trending_news", 3 if kind == "official" else 2,
                        kind, "facts_only", identifier)


def test_topic_ranking_accepts_official_source_and_rejects_repeats(repo_root: Path):
    config = load_config(repo_root / "config" / "kpop.yaml")
    state = json.loads((repo_root / "data" / "kpop_state.json").read_text(encoding="utf-8"))
    source = _source("one")
    source = SourceRecord(**{**source.__dict__, "published_at": datetime.now(timezone.utc).isoformat()})
    topics = rank_topics([source], state, config)
    assert topics and topics[0].review_reason == ""
    state["used_articles"] = ["one"]
    assert rank_topics([source], state, config) == []


def test_all_eight_formats_generate_only_cited_content():
    assert len(STRUCTURES) == 8
    source = _source("one")
    for category in STRUCTURES:
        topic = Topic("topic-" + category, source.title, category, "IVE", (source,),
                      (source.title, source.evidence))
        script = generate_script(topic)
        assert script["source_ids"] == ["one"]
        assert "Official" in script["narration"]
        assert 30 <= script["word_count"] <= 135


def test_state_slot_and_upload_are_idempotent():
    state = {"used_articles": [], "covered_topics": [], "entity_history": [], "hook_history": [],
             "pending": {}, "uploads": {}, "slots": {}, "analytics": []}
    manifest = {"content_id": "c1", "slot_id": "2026-09-23T07:00", "status": "pending_approval",
                "created_at": "now", "topic": {"topic_id": "t1", "category": "trending_news", "entity": "IVE"},
                "script": {"source_ids": ["s1"], "hook": "Verified update"}}
    queue_manifest(state, manifest)
    with pytest.raises(ValueError):
        queue_manifest(state, manifest)
    result = {"status": "success", "youtube_video_id": "abc", "privacy_status": "private"}
    finalize_upload(state, "c1", result)
    finalize_upload(state, "c1", result)
    assert state["uploads"]["c1"]["youtube_video_id"] == "abc"


def test_approved_asset_registry_is_fail_closed(repo_root: Path):
    assert load_approved_assets(repo_root) == {}


def test_fixture_cannot_be_used_outside_dry_run(repo_root: Path):
    with pytest.raises(ValueError, match="only with --dry-run"):
        produce(repo_root, repo_root / "config" / "kpop.yaml", "unsafe-slot", fixture=repo_root / "tests/fixtures/verified_topic.json")


def test_workflows_cover_review_recovery_analytics_and_tests(repo_root: Path):
    names = {path.name for path in (repo_root / ".github/workflows").glob("*.yml")}
    assert {"kpop-production.yml", "kpop-approval.yml", "kpop-dry-run.yml", "kpop-recovery.yml",
            "kpop-catch-up.yml", "kpop-analytics.yml", "kpop-weekly-report.yml", "tests.yml"} <= names
