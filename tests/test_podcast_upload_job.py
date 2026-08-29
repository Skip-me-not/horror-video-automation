from scripts.build_podcast_upload_job import build_job


def test_build_job_credits_source_and_targets_horror_shorts(monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    job = build_job(
        {"title": "Haunted Chapel", "channel": "Ghost Podcast",
         "source_url": "https://example.com/episode"},
        {"text": "This chapel has a secret."},
    )
    assert job["job_id"] == "12345"
    assert job["title"] == "Haunted Chapel"
    assert "Ghost Podcast" in job["description"]
    assert "https://example.com/episode" in job["description"]
    assert {"horror", "podcast", "shorts"}.issubset(job["tags"])
