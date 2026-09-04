from __future__ import annotations

from pathlib import Path

from src.incident_bank import IncidentBank
from src.subtitles import SubtitleWriter


def test_production_incident_bank_is_valid():
    bank = IncidentBank(Path("data/incident_bank.json"), Path("data/used_scripts.json"))
    assert len(bank.items) >= 20
    assert not bank.validate()


def test_important_caption_terms_are_pink(tmp_path):
    timings = [
        {"text": "In", "offset": 0.0, "duration": 0.2},
        {"text": "1959", "offset": 0.2, "duration": 0.3},
        {"text": "nine", "offset": 0.5, "duration": 0.2},
        {"text": "hikers", "offset": 0.7, "duration": 0.3},
    ]
    output = tmp_path / "captions.ass"
    SubtitleWriter().from_timings(timings, output, ["nine hikers", "1959"])
    content = output.read_text(encoding="utf-8")
    assert r"{\c&H00D86BFF&}1959" in content
    assert r"{\c&H00D86BFF&}NINE" in content
    assert "WrapStyle: 0" in content
    assert "Style: Main,DejaVu Sans,68" in content
    assert ",5,120,120,0,1" in content


def test_long_caption_uses_smaller_font(tmp_path):
    timings = [
        {"text": "UNEXPLAINED", "offset": 0.0, "duration": 0.3},
        {"text": "DISAPPEARANCE", "offset": 0.3, "duration": 0.4},
    ]
    output = tmp_path / "captions.ass"
    SubtitleWriter().from_timings(timings, output)
    content = output.read_text(encoding="utf-8")
    assert r"\fs50" in content
