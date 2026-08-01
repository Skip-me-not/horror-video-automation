from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def config() -> dict:
    return json.loads((ROOT / "config/default.json").read_text(encoding="utf-8"))


@pytest.fixture
def valid_job() -> dict:
    return {
        "job_id": "safe-job-1",
        "title": "A Safe Title",
        "story": "A quiet sentence. " * 12,
        "description": "Description",
        "tags": ["horror"],
        "background_file": "background.mp4",
        "ambience_file": "",
        "thumbnail_file": "",
        "privacy_status": "private",
    }

