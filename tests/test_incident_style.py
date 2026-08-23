from __future__ import annotations

from pathlib import Path

from src.incident_bank import IncidentBank
from src.subtitles import SubtitleWriter


def test_production_incident_bank_is_valid():
    bank = IncidentBank(Path("data/incident_bank.json"), Path("data/used_scripts.json"))
    assert len(bank.items) >= 20
    assert not bank.validate()


def test_important_caption_terms_are_red(tmp_path):
    timings = [
        {"text": "In", "offset": 0.0, "duration": 0.2},
        {"text": "1959", "offset": 0.2, "duration": 0.3},
        {"text": "nine", "offset": 0.5, "duration": 0.2},
        {"text": "hikers", "offset": 0.7, "duration": 0.3},
    ]
    output = tmp_path / "captions.ass"
    SubtitleWriter().from_timings(timings, output, ["nine hikers", "1959"])
    content = output.read_text(encoding="utf-8")
    assert r"{\c&H000000FF&}1959" in content
    assert r"{\c&H000000FF&}NINE" in content
    assert "Style: Main,DejaVu Sans,86" in content
