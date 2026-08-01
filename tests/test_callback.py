from scripts.notify_n8n import build_callback_payload


def test_callback_payload_whitelists_result_fields():
    payload = build_callback_payload(
        "job-1", "success",
        {"youtube_video_id": "abc", "watch_url": "https://example.test",
         "privacy_status": "private", "secret": "do-not-copy"},
    )
    assert payload["youtube_video_id"] == "abc"
    assert "secret" not in payload


def test_callback_error_is_bounded():
    payload = build_callback_payload("job-1", "failure", None, "x" * 2000)
    assert len(payload["error"]) == 1000

