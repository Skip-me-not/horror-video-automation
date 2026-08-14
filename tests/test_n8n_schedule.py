import json
import re
from pathlib import Path


def test_n8n_owns_the_upload_schedule_without_github_duplicates():
    workflow = json.loads(Path("n8n/horror-video-orchestrator.json").read_text(encoding="utf-8"))
    nodes = {node["name"]: node for node in workflow["nodes"]}

    schedule = nodes["Daily Schedule"]
    assert schedule["type"] == "n8n-nodes-base.scheduleTrigger"
    assert schedule["parameters"]["rule"]["interval"] == [
        {"field": "cronExpression", "expression": "30 5,8,11,14 * * *"}
    ]
    assert workflow["settings"]["timezone"] == "Asia/Yangon"
    assert workflow["connections"]["Daily Schedule"]["main"][0][0]["node"] == "Prepare Scheduled Run"
    assert workflow["connections"]["Prepare Scheduled Run"]["main"][0][0]["node"] == "Dispatch Scheduled Story"

    scheduled_body = nodes["Dispatch Scheduled Story"]["parameters"]["body"]
    assert "tts_provider" in scheduled_body
    assert "job_payload" not in scheduled_body
    assert "idea_number" not in scheduled_body

    github_workflow = Path(".github/workflows/create-horror-video.yml").read_text(encoding="utf-8")
    assert not re.search(r"^\s{2}schedule:\s*$", github_workflow, flags=re.MULTILINE)


def test_n8n_custom_story_limits_match_retention_config():
    workflow = json.loads(Path("n8n/horror-video-orchestrator.json").read_text(encoding="utf-8"))
    nodes = {node["name"]: node for node in workflow["nodes"]}
    validation_code = nodes["Validate Input"]["parameters"]["jsCode"]

    assert "180" in validation_code
    assert "1100" in validation_code
    assert "Skip-me-not" in nodes["Prepare Scheduled Run"]["parameters"]["jsCode"]
    assert "horror-video-automation" in nodes["Prepare Scheduled Run"]["parameters"]["jsCode"]
