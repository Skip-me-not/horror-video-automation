from pathlib import Path

import pytest

import src.tts as tts


def test_tts_retries_empty_service_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    narrator = tts.EdgeTTSNarrator("test")
    calls = []

    async def intermittent(_text, audio_path, _timing_path):
        calls.append(1)
        if len(calls) < 3:
            audio_path.write_bytes(b"partial")
            raise RuntimeError("No audio was received")
        return [{"text": "ready", "offset": 0.0, "duration": 0.2}]

    monkeypatch.setattr(narrator, "_synthesize", intermittent)
    monkeypatch.setattr(tts.time, "sleep", lambda _seconds: None)
    audio = tmp_path / "voice.mp3"
    assert narrator.synthesize("ready", audio, tmp_path / "timings.json") == [
        {"text": "ready", "offset": 0.0, "duration": 0.2}
    ]
    assert len(calls) == 3
    assert not audio.exists()
