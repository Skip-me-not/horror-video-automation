from __future__ import annotations

import json
import os
import random
import uuid
from pathlib import Path
from typing import Any

from .config import Settings
from .metadata_generator import MetadataGenerator
from .quality_check import VideoQualityChecker
from .renderer import ExistingMediaPipelineRenderer
from .scene_generator import SceneGenerator
from .script_bank import ScriptBank, atomic_write_json, utc_now
from .youtube_upload import upload_video


class HorrorShortPipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.settings.validate()
        self.bank = ScriptBank(self.settings.bank_path, self.settings.used_path)
        self.metadata_generator = MetadataGenerator()
        self.scene_generator = SceneGenerator()

    def _state(self) -> dict[str, Any]:
        if not self.settings.state_path.exists():
            return {"version": 1, "pending_script_id": None, "last_success": None}
        state = json.loads(self.settings.state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("generation_state.json must contain an object")
        return state

    def reserve(self, script_id: str | None = None, *, persist: bool = True) -> dict[str, object]:
        state = self._state()
        pending = state.get("pending_script_id")
        if pending:
            try:
                script = self.bank.get(str(pending))
                if script.get("status") == "ready":
                    return self._prepare(script, state)
            except KeyError:
                pass
        script = self.bank.get(script_id) if script_id else self.bank.select_unused()
        if script.get("status") != "ready":
            raise ValueError(f"script {script['id']} is not READY")
        state.update({
            "pending_script_id": script["id"],
            "pending_job_id": f"hs-{script['id'].lower()}-{uuid.uuid4().hex[:8]}",
            "reserved_at": utc_now(),
            "stage": "reserved",
        })
        if persist:
            atomic_write_json(self.settings.state_path, state)
        return self._prepare(script, state)

    def _prepare(self, script: dict[str, object], state: dict[str, Any]) -> dict[str, object]:
        metadata = self.metadata_generator.generate(script)
        errors = self.metadata_generator.validate(metadata)
        if errors:
            raise ValueError("metadata invalid: " + "; ".join(errors))
        scenes = self.scene_generator.generate(script)
        job = {
            "job_id": state.get("pending_job_id") or f"hs-{str(script['id']).lower()}",
            "script_id": script["id"],
            "title": metadata["title"],
            "story": script["script"],
            "description": metadata["description"] + "\n\n" + " ".join(metadata["hashtags"]),
            "tags": [str(tag).lstrip("#") for tag in metadata["hashtags"]] + [str(script["category"]).lower()],
            "genre": script["category"],
            "background_file": "dark-corridor.png",
            "background_query": scenes[0]["visual_prompt"],
            "background_queries": [scene["visual_prompt"] for scene in scenes],
            "ambience_file": "",
            "thumbnail_file": "",
            "watermark_text": "",
            "privacy_status": self.settings.upload_privacy,
            "scenes": scenes,
        }
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.settings.output_dir / "job.json", job)
        atomic_write_json(self.settings.output_dir / "pipeline-plan.json", {
            "script": script, "metadata": metadata, "scenes": scenes, "job": job,
        })
        return job

    def run(self, *, dry_run: bool = False, no_upload: bool = False,
            script_id: str | None = None) -> dict[str, object]:
        job = self.reserve(script_id, persist=not dry_run)
        script = self.bank.get(str(job["script_id"]))
        plan = json.loads((self.settings.output_dir / "pipeline-plan.json").read_text(encoding="utf-8"))
        if dry_run:
            return {"status": "dry-run", "script_id": script["id"], "plan": str(self.settings.output_dir / "pipeline-plan.json")}
        state = self._state()
        state["stage"] = "rendering"
        atomic_write_json(self.settings.state_path, state)
        try:
            video = ExistingMediaPipelineRenderer(self.settings.root).render(self.settings.output_dir / "job.json")
            metadata = plan["metadata"]
            narration = self.settings.output_dir / "narration.mp3"
            if not narration.exists():
                narration = self.settings.output_dir / "narration.wav"
            report = VideoQualityChecker().check(
                video, narration,
                self.settings.output_dir / "captions.ass", script, metadata,
            )
            if not report.valid:
                raise RuntimeError("quality check failed: " + "; ".join(report.errors))
            if no_upload:
                state["stage"] = "rendered_no_upload"
                atomic_write_json(self.settings.state_path, state)
                return {"status": "rendered", "script_id": script["id"], "video": str(video)}
            state["stage"] = "uploading"
            atomic_write_json(self.settings.state_path, state)
            result = upload_video(video, job, self.settings.root, self.settings.upload_privacy)
            video_id = str(result.get("youtube_video_id", ""))
            if not video_id:
                raise RuntimeError("YouTube upload returned no video ID")
            self.bank.mark_used(str(script["id"]), video_id)
            state.update({
                "stage": "complete", "pending_script_id": None, "pending_job_id": None,
                "last_success": {"script_id": script["id"], "youtube_video_id": video_id, "completed_at": utc_now()},
            })
            atomic_write_json(self.settings.state_path, state)
            return result
        except Exception:
            # Intentionally preserve READY status and reservation for a safe retry.
            state["stage"] = "failed"
            state["failed_at"] = utc_now()
            atomic_write_json(self.settings.state_path, state)
            raise
