from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from src.config import Settings
from src.duplicate_detector import DuplicateDetector, normalize, similarity
from src.fact_source_provider import normalize_loc_result
from src.metadata_generator import MetadataGenerator
from src.pipeline import HorrorShortPipeline
from src.script_bank import REQUIRED_FIELDS, ScriptBank, atomic_write_json
from src.script_judge import ScriptJudge


def ready_script(script_id: str = "HF0001", category: str = "Ghost Oral History") -> dict[str, object]:
    script = (
        "Here is a horror fact most people do not know: Ghost Story is a real cataloged archive item. "
        "The Library of Congress dates the record to 1939 and connects it to a named performer in Taylor, Texas. "
        "Its catalog subjects include ghost stories and folklore. The archive verifies that this account was recorded; "
        "it does not prove a supernatural explanation. The direct item page is linked for independent checking."
    )
    return {
        "id": script_id, "content_type": "sourced_horror_fact", "evidence_type": "oral_history",
        "category": category, "location": "Taylor, Texas", "source_id": f"source-{script_id}",
        "source_title": "Ghost Story", "source_url": f"https://www.loc.gov/item/{script_id.lower()}/",
        "source_institution": "Library of Congress", "source_date": "1939-05-10",
        "source_collection": "John and Ruby Lomax collection", "source_rights": "See item page.",
        "verification_note": "The archival record is verified; supernatural interpretation is not verified.",
        "title": "The 1939 Ghost Account Preserved in an Archive",
        "hook": "Here is a horror fact most people do not know: Ghost Story is a real cataloged archive item.", "script": script,
        "word_count": len(script.split()), "estimated_duration": 27.0, "quality_score": 45,
        "similarity_score": 0.0, "status": "ready", "created_at": "2026-01-01T00:00:00+00:00",
        "used_at": None, "youtube_video_id": None,
        "plot_fingerprint": f"source|{script_id.lower()}",
    }


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        root=tmp_path, bank_path=tmp_path / "data/script_bank.json",
        used_path=tmp_path / "data/used_scripts.json", state_path=tmp_path / "data/generation_state.json",
        performance_path=tmp_path / "data/performance.json", output_dir=tmp_path / "output",
    )


def test_script_bank_parsing_and_required_schema(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    atomic_write_json(settings.bank_path, [ready_script()])
    bank = ScriptBank(settings.bank_path, settings.used_path)
    assert not bank.validate()
    assert REQUIRED_FIELDS <= set(bank.items[0])


def test_invalid_bank_json_fails_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "bank.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        ScriptBank(path)


def test_duplicate_detector_checks_exact_title_hook_story_and_fingerprint() -> None:
    item = ready_script()
    detector = DuplicateDetector()
    assert detector.check(dict(item), [item]).duplicate
    changed = dict(item, id="HF0002", title="A Completely Different Archive Title")
    assert detector.check(changed, [item]).duplicate  # exact story still blocks it
    assert normalize("  HeLLo, WORLD! ") == "hello world"
    assert similarity("same short phrase", "same short phrase") == 1.0


def test_similarity_threshold_is_configurable() -> None:
    original = ready_script()
    candidate = dict(original, id="HF0002", title="Different", hook="Different", script="Entirely different words form a separate source record.",
                     plot_fingerprint="source|different", source_id="different", source_url="https://www.loc.gov/item/different/")
    assert not DuplicateDetector(story_threshold=0.99).check(candidate, [original]).duplicate


def test_mark_used_is_the_only_status_transition(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    atomic_write_json(settings.bank_path, [ready_script()])
    bank = ScriptBank(settings.bank_path, settings.used_path)
    bank.mark_used("HF0001", "youtube123")
    assert bank.get("HF0001")["status"] == "used"
    assert bank.get("HF0001")["youtube_video_id"] == "youtube123"
    assert json.loads(settings.used_path.read_text(encoding="utf-8"))[0]["id"] == "HF0001"
    with pytest.raises(ValueError, match="not READY"):
        bank.mark_used("HF0001", "second")


def test_selection_prefers_category_not_recently_used(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    first, second = ready_script(), ready_script("HF0002", "Witchcraft Record")
    second["title"] = "The Hotel Room Added Itself"
    atomic_write_json(settings.bank_path, [first, second])
    atomic_write_json(settings.used_path, [{"category": "Ghost Oral History"}] * 4)
    selected = ScriptBank(settings.bank_path, settings.used_path).select_unused(random.Random(2))
    assert selected["category"] == "Witchcraft Record"


def test_metadata_and_quality_validation() -> None:
    script = ready_script()
    metadata = MetadataGenerator().generate(script)
    assert not MetadataGenerator.validate(metadata)
    assert 40 <= ScriptJudge().score(script).total <= 50
    bad = dict(metadata, title="TRUE STORY: Something")
    assert "unsupported TRUE STORY claim" in MetadataGenerator.validate(bad)


def test_dry_run_does_not_change_persistent_state(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    atomic_write_json(settings.bank_path, [ready_script()])
    original = {"version": 1, "stage": "idle", "pending_script_id": None}
    atomic_write_json(settings.state_path, original)
    result = HorrorShortPipeline(settings).run(dry_run=True)
    assert result["status"] == "dry-run"
    assert json.loads(settings.state_path.read_text(encoding="utf-8")) == original
    assert ScriptBank(settings.bank_path).get("HF0001")["status"] == "ready"


def test_failed_upload_keeps_script_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for(tmp_path)
    atomic_write_json(settings.bank_path, [ready_script()])

    class FakeRenderer:
        def __init__(self, root: Path) -> None:
            self.root = root
        def render(self, job_path: Path) -> Path:
            output = self.root / "output"
            output.mkdir(parents=True, exist_ok=True)
            for name in ("final.mp4", "narration.wav", "captions.ass"):
                (output / name).write_bytes(b"valid-test-data")
            return output / "final.mp4"

    class FakeChecker:
        def check(self, *args, **kwargs):
            return type("Report", (), {"valid": True, "errors": ()})()

    monkeypatch.setattr("src.pipeline.ExistingMediaPipelineRenderer", FakeRenderer)
    monkeypatch.setattr("src.pipeline.VideoQualityChecker", FakeChecker)
    monkeypatch.setattr("src.pipeline.upload_video", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("upload failed")))
    with pytest.raises(RuntimeError, match="upload failed"):
        HorrorShortPipeline(settings).run()
    bank = ScriptBank(settings.bank_path, settings.used_path)
    assert bank.get("HF0001")["status"] == "ready"
    assert bank.get("HF0001")["youtube_video_id"] is None


def test_loc_metadata_normalization_labels_the_record_not_the_claim() -> None:
    source = normalize_loc_result({
        "url": "https://www.loc.gov/item/wpalh001937/", "title": "[Ghost Story]", "date": "1938-11-16",
        "original_format": ["interview (text)"], "subject": ["Ghost stories", "Folklore"],
        "item": {"created_published": ["New York City, 1938"], "contributors": ["West, Dorothy"]},
    })
    assert source is not None
    assert source.evidence_type == "oral_history"
    assert source.source_institution == "Library of Congress"
