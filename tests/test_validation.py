from __future__ import annotations

import base64
import json

import pytest

from scripts.common import ValidationError, safe_filename, sanitize_output_name
from scripts.validate_job import decode_payload, validate_job
from scripts.upload_youtube import shorts_description, shorts_title


def test_valid_job_is_normalized(valid_job, config):
    result = validate_job(valid_job, config)
    assert result["privacy_status"] == "private"
    assert result["callback_url"] == ""


@pytest.mark.parametrize("story", ["", "too short"])
def test_rejects_short_or_empty_story(valid_job, config, story):
    valid_job["story"] = story
    with pytest.raises(ValidationError, match="story"):
        validate_job(valid_job, config)


def test_rejects_too_long_story(valid_job, config):
    valid_job["story"] = "x" * (config["max_story_characters"] + 1)
    with pytest.raises(ValidationError, match="story"):
        validate_job(valid_job, config)


@pytest.mark.parametrize("name", ["../clip.mp4", "..\\clip.mp4", "/tmp/clip.mp4", "x.sh"])
def test_rejects_path_traversal_and_unsupported_media(name):
    with pytest.raises(ValidationError):
        safe_filename(name, "background_file")


def test_payload_size_and_base64_validation(valid_job, config):
    encoded = base64.b64encode(json.dumps(valid_job).encode()).decode()
    assert decode_payload(encoded, config["max_payload_bytes"])["job_id"] == "safe-job-1"
    with pytest.raises(ValidationError):
        decode_payload("not base64!", config["max_payload_bytes"])
    with pytest.raises(ValidationError, match="large"):
        decode_payload(encoded, 4)


def test_output_filename_sanitization():
    assert sanitize_output_name(" Room 17 / Finale!! ") == "room-17-finale.mp4"
    assert sanitize_output_name("...") == "video.mp4"


def test_rejects_non_text_callback(valid_job, config):
    valid_job["callback_url"] = []
    with pytest.raises(ValidationError, match="callback"):
        validate_job(valid_job, config)


def test_youtube_metadata_is_short_safe():
    title = shorts_title("The Thing Behind the Door " * 10)
    assert len(title) <= 100
    assert title.endswith("#shorts")
    description = shorts_description("A thirty-second original horror story.")
    assert "#horror" in description
    assert "#shorts" in description
