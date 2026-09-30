from __future__ import annotations

import json
from pathlib import Path

import pytest

from bot.parser import parse_short
from bot.telegram_bot import authorize, dispatch, sync_local_jobs
from pipeline.dispatch_job import load_event
from pipeline.job import first_hook, validate_job
from pipeline.job_state import complete, reserve, visible
from pipeline.scene_builder import build
from providers.user_urls import approved_record


def test_telegram_parser_multiline_defaults_and_exact_title():
    job = parse_short("/short\nPERSON: Jennie BLACKPINK\nTITLE: A title 😳\nSCRIPT: One complete user sentence.\n"
                      "Another line of narration goes here.\nMEDIA: automatic")
    assert job["title"] == "A title 😳"
    assert "Another line" in job["script"]
    assert job["voice"] == "en-US-AriaNeural"
    assert job["privacy"] == "private"
    assert job["upload"] == "youtube"
    assert job["content_hash"] == job["dedupe_key"]


def test_burmese_labels_and_no_fabricated_hook():
    job = parse_short("/short\nနာမည်: ဂျင်နီ\nစာသား: ဒီဗီဒီယိုမှာ အသုံးပြုသူရေးထားတဲ့စာသားကိုသာ ဖတ်ပြပါမယ်။ "
                      "သတင်းအချက်အလက်အသစ် မတီထွင်ပါ။")
    assert job["person"] == "ဂျင်နီ"
    assert job["title"].startswith("ဂျင်နီ")
    assert first_hook(job["script"]) in job["script"]


def test_reject_invalid_or_duplicate_fields():
    with pytest.raises(ValueError, match="PERSON"):
        parse_short("/short\nSCRIPT: This is a long enough sample narration for testing.")
    with pytest.raises(ValueError, match="Duplicate"):
        parse_short("/short\nPERSON: A name\nPERSON: Second name\nSCRIPT: A valid long narration here.")
    with pytest.raises(ValueError, match="VOICE"):
        validate_job({"job_id": "good", "person": "Person", "script": "A valid long narration for the job.",
                      "voice": "$(bad)"})
    assert first_hook("This opening sentence contains so many words that it must be visually shortened without adding new information at all.").endswith("…")


def test_allowlists_require_matching_sender_and_chat(monkeypatch):
    monkeypatch.setenv("ALLOWED_TELEGRAM_USER_IDS", "1")
    monkeypatch.setenv("ALLOWED_TELEGRAM_CHAT_IDS", "-2")
    assert authorize(1, -2)
    assert not authorize(3, -2)
    assert not authorize(1, -4)


class _Response:
    def __init__(self, status: int):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Session:
    def __init__(self, status: int = 404):
        self.status = status
        self.posted = None

    def get(self, *args, **kwargs):
        return _Response(self.status)

    def post(self, url, **kwargs):
        self.posted = kwargs["json"]
        return _Response(204)


def test_dispatch_rejects_duplicates_before_trigger(monkeypatch):
    monkeypatch.setenv("GH_PAT", "test-token")
    job = validate_job({"job_id": "job1", "person": "Jennie", "script": "A sufficiently long script for this test job."})
    session = _Session()
    dispatch(job, 123, session=session)
    assert session.posted["client_payload"]["job"]["title"] == "Jennie — Latest Short Update"
    duplicate = _Session(200)
    with pytest.raises(ValueError, match="already submitted"):
        dispatch(job, 123, session=duplicate)
    assert duplicate.posted is None


def test_dispatch_event_keeps_script_out_of_repository(tmp_path: Path):
    job = {"job_id": "event1", "person": "A Person", "script": "This is the user's complete script for a safe test."}
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"client_payload": {"job": job, "chat_id": 123}}), encoding="utf-8")
    loaded, chat = load_event(path)
    assert loaded["job_id"] == "event1"
    assert chat == "123"


def test_bot_moves_local_job_after_matching_actions_success(monkeypatch, tmp_path: Path):
    from bot import telegram_bot

    monkeypatch.setattr(telegram_bot, "ROOT", tmp_path)
    monkeypatch.setenv("GH_PAT", "test-token")
    pending = tmp_path / "jobs" / "pending"
    pending.mkdir(parents=True)
    (pending / "job42.json").write_text('{"job_id":"job42"}', encoding="utf-8")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"workflow_runs": [{"display_title": "Telegram Short job42",
                                       "status": "completed", "conclusion": "success"}]}

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    assert sync_local_jobs(session=Session()) == 1
    assert (tmp_path / "jobs" / "private_completed" / "job42.json").is_file()


def test_reserve_complete_and_visibility_are_idempotent(monkeypatch, tmp_path: Path):
    from pipeline import job_state

    monkeypatch.setattr(job_state, "ROOT", tmp_path)
    job = validate_job({"job_id": "j1", "person": "Jennie", "script": "This is a complete test script for a private upload."})
    reserve(job)
    with pytest.raises(ValueError, match="already reserved"):
        reserve(job)
    result = {"status": "success", "youtube_video_id": "abc", "privacy_status": "private"}
    receipt = complete(job, result)
    assert not (tmp_path / "jobs" / "locks" / f"{job['dedupe_key']}.json").exists()
    result["privacy_status"] = "public"
    visible(job, result)
    assert json.loads(receipt.read_text(encoding="utf-8"))["privacy_status"] == "public"
    with pytest.raises(ValueError, match="already reserved or uploaded"):
        reserve(job)


def test_scene_builder_varies_pacing_and_avoids_immediate_repeats(tmp_path: Path):
    cards = [{"id": f"c{i}", "path": f"{i}.png", "license": "original-generated"} for i in range(20)]
    scenes = build(cards, [], 40.0, tmp_path)
    assert sum(item["duration"] for item in scenes) == pytest.approx(40)
    assert len({round(item["duration"], 2) for item in scenes}) > 3
    assert all(left["id"] != right["id"] for left, right in zip(scenes, scenes[1:]))
    assert (tmp_path / "timeline.json").is_file()


def test_unapproved_telegram_url_is_not_downloaded(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "telegram_media_approvals.json").write_text('{"assets": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="no exact"):
        approved_record(tmp_path, "https://example.com/celebrity.jpg")


def test_youtube_upload_preserves_exact_user_title(monkeypatch, tmp_path: Path):
    from pipeline import youtube_upload

    video = tmp_path / "final.mp4"
    video.write_bytes(b"x" * 500_001)
    job = validate_job({"job_id": "yt1", "person": "Jennie", "title": "Exact title 😳",
                        "script": "A fully authored narration with enough text for validation."})
    captured = {}

    class Videos:
        def insert(self, **kwargs):
            captured.update(kwargs)
            return object()

    class YouTube:
        def videos(self):
            return Videos()

    monkeypatch.setattr(youtube_upload, "build", lambda *args, **kwargs: YouTube())
    monkeypatch.setattr(youtube_upload, "credentials_from_environment", lambda: object())
    monkeypatch.setattr(youtube_upload, "execute_resumable", lambda request: {"id": "video123"})
    result = youtube_upload.upload(video, job)
    assert captured["body"]["snippet"]["title"] == "Exact title 😳"
    assert captured["body"]["status"]["privacyStatus"] == "private"
    assert result["youtube_video_id"] == "video123"


def test_dispatch_workflow_reserves_before_private_upload(repo_root: Path):
    content = (repo_root / ".github" / "workflows" / "render-short.yml").read_text(encoding="utf-8")
    assert "repository_dispatch:" in content and "types: [render_short]" in content
    assert content.index("Reserve content hash") < content.index("Upload validated Short privately")
    assert content.index("Persist confirmed private video ID") < content.index("Apply requested YouTube visibility")
    assert "--privacy private" in content
    assert "schedule:" not in content
