from __future__ import annotations

import pytest

import scripts.generate_voice as voice
from scripts.common import ValidationError


def test_chunking_preserves_all_words_and_sentence_endings():
    text = (
        "The first door closed quietly. The second door never opened. "
        "Something waited behind it.\n\nNobody returned after midnight."
    )
    chunks = voice.split_text(text, 55)
    assert " ".join(" ".join(chunks).split()) == " ".join(text.split())
    assert all(chunk for chunk in chunks)
    assert any(chunk.endswith(".") for chunk in chunks)


def test_oversized_sentence_splits_on_words_without_loss():
    text = " ".join(f"word{i}" for i in range(50)) + "."
    chunks = voice.split_text(text, 100)
    assert " ".join(chunks) == text
    assert all(len(chunk) <= 100 for chunk in chunks)


def test_paragraph_and_section_pauses_are_preserved():
    text = "First sentence.\n\nSecond sentence.\n\n\nThird sentence."
    chunks = voice.split_text(text, 100)
    assert voice.pauses_for_chunks(text, chunks, 600, 900) == [600, 900, 0]


def test_provider_selection_is_explicit(monkeypatch, config):
    monkeypatch.setattr(voice, "ChatterboxNanoProvider", lambda c: ("chatterbox", c))
    monkeypatch.setattr(voice, "KokoroProvider", lambda c: ("kokoro", c))
    assert voice.create_provider("chatterbox", config)[0] == "chatterbox"
    assert voice.create_provider("kokoro", config)[0] == "kokoro"
    with pytest.raises(ValidationError):
        voice.create_provider("automatic", config)


def test_short_caption_cards_preserve_story_text():
    story = (
        "The hallway light blinked twice. Something behind Mara copied her breathing. "
        "She held her breath, but the sound continued."
    )
    captions = voice.split_captions(story, 55)
    assert len(captions) >= 2
    assert all(len(caption) <= 55 for caption in captions)
    assert " ".join(captions) == story


def test_ass_captions_stay_inside_short_narration_window(config, tmp_path):
    output = tmp_path / "captions.ass"
    voice.write_captions("The locked door whispered her name. She never answered.", 12, config, output)
    content = output.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "Dialogue: 0,0:00:00.10" in content
    assert "THE LOCKED DOOR WHISPERED" in content
    assert "ANSWERED." in content
    assert r"\fscx108" in content
    assert r"\N" in content
