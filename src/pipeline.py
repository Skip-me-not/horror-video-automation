from __future__ import annotations

import json
import os
import random
import uuid
from pathlib import Path
from typing import Any

from .config import Settings
from .fact_bundle import build_narration
from .incident_bank import IncidentBank
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
        incident_path = self.settings.root / "data" / "incident_bank.json"
        self.incidents = IncidentBank(incident_path, self.settings.used_path) if incident_path.exists() else None
        if self.incidents:
            incident_errors = self.incidents.validate()
            if incident_errors:
                raise ValueError("incident bank invalid: " + "; ".join(incident_errors))
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
        if self.incidents:
            pending_incident = state.get("pending_incident_id")
            if pending_incident:
                try:
                    incident = self.incidents.get(str(pending_incident))
                    if incident.get("status") == "ready":
                        return self._prepare_incident(incident, state)
                except KeyError:
                    pass
            incident = self.incidents.get(script_id) if script_id else self.incidents.select_unused()
            if incident.get("status") != "ready":
                raise ValueError(f"incident {incident['id']} is not READY")
            state.update({
                "pending_incident_id": incident["id"], "pending_script_id": incident["id"],
                "pending_script_ids": [],
                "pending_job_id": f"event-{str(incident['id']).lower()}-{uuid.uuid4().hex[:8]}",
                "reserved_at": utc_now(), "stage": "reserved",
            })
            if persist:
                atomic_write_json(self.settings.state_path, state)
            return self._prepare_incident(incident, state)
        pending_ids = state.get("pending_script_ids") or ([state.get("pending_script_id")] if state.get("pending_script_id") else [])
        if pending_ids:
            try:
                scripts = [self.bank.get(str(value)) for value in pending_ids]
                if scripts and all(script.get("status") == "ready" for script in scripts):
                    return self._prepare(scripts, state)
            except KeyError:
                pass
        scripts = self.bank.select_unused_many(5, first_id=script_id)
        if not scripts:
            raise RuntimeError("no unused READY scripts remain")
        state.update({
            "pending_script_id": scripts[0]["id"],
            "pending_script_ids": [script["id"] for script in scripts],
            "pending_job_id": f"hs-{str(scripts[0]['id']).lower()}-{uuid.uuid4().hex[:8]}",
            "reserved_at": utc_now(),
            "stage": "reserved",
        })
        if persist:
            atomic_write_json(self.settings.state_path, state)
        return self._prepare(scripts, state)

    def _prepare_incident(self, incident: dict[str, object], state: dict[str, Any]) -> dict[str, object]:
        title = str(incident["title"]).strip()[:100]
        metadata = {
            "title": title,
            "description": (
                "A documented strange incident, explained from the surviving record. "
                "Reported or disputed claims are identified as such.\n\n"
                f"Source: {incident['source_url']}\nSource title: {incident['source_title']}"
            ),
            "hashtags": ["#strangeevents", "#darkhistory", "#shorts"],
        }
        errors = self.metadata_generator.validate(metadata)
        if errors:
            raise ValueError("metadata invalid: " + "; ".join(errors))
        scenes = self.scene_generator.generate_incident(incident)
        background_queries = [scene["visual_prompt"] for scene in scenes for _ in range(2)]
        job = {
            "job_id": state.get("pending_job_id") or f"event-{str(incident['id']).lower()}",
            "script_id": incident["id"], "script_ids": [incident["id"]],
            "content_type": "documented_strange_incident",
            "title": title, "story": f"{incident['hook']} {incident['script']}",
            "description": metadata["description"] + "\n\n" + " ".join(metadata["hashtags"]),
            "tags": ["strange events", "dark history", "unsolved mystery", "shorts"],
            "genre": "Documented Strange Incident", "background_file": "dark-corridor.png",
            "background_query": scenes[0]["visual_prompt"], "background_queries": background_queries,
            "important_terms": incident["important_terms"],
            "ambience_file": "", "thumbnail_file": "", "watermark_text": "",
            "privacy_status": self.settings.upload_privacy, "scenes": scenes,
        }
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.settings.output_dir / "job.json", job)
        atomic_write_json(self.settings.output_dir / "pipeline-plan.json", {
            "incident": incident, "metadata": metadata, "scenes": scenes, "job": job,
        })
        return job

    def _prepare(self, scripts: list[dict[str, object]], state: dict[str, Any]) -> dict[str, object]:
        script = scripts[0]
        metadata = self.metadata_generator.generate(script)
        metadata["title"] = f"{len(scripts)} Horror Facts You Weren't Supposed to Know"
        source_lines = "\n".join(
            (f"Source: {item['source_url']} ({item['source_title']})" if index == 1
             else f"Source {index}: {item['source_url']} ({item['source_title']})")
            for index, item in enumerate(scripts, 1)
        )
        metadata["description"] = (
            f"{len(scripts)} documented horror and folklore facts, presented as reported beliefs—not paranormal proof.\n\n"
            f"Sources:\n{source_lines}"
        )
        errors = self.metadata_generator.validate(metadata)
        if errors:
            raise ValueError("metadata invalid: " + "; ".join(errors))
        scenes = self.scene_generator.generate_bundle(scripts)
        story = build_narration(scripts)
        intro_query = (
            "dark room of vintage CRT televisions showing static, blood red HORROR FACTS title, "
            "analog VHS interference, black background, vertical 9:16"
        )
        background_queries = [intro_query, *[scene["visual_prompt"] for scene in scenes for _ in range(2)]]
        job = {
            "job_id": state.get("pending_job_id") or f"hs-{str(script['id']).lower()}",
            "script_id": script["id"],
            "script_ids": [item["id"] for item in scripts],
            "title": metadata["title"],
            "story": story,
            "description": metadata["description"] + "\n\n" + " ".join(metadata["hashtags"]),
            "tags": [str(tag).lstrip("#") for tag in metadata["hashtags"]] + [str(script["category"]).lower()],
            "genre": script["category"],
            "background_file": "dark-corridor.png",
            "background_query": scenes[0]["visual_prompt"],
            "background_queries": background_queries,
            "ambience_file": "",
            "thumbnail_file": "",
            "watermark_text": "",
            "privacy_status": self.settings.upload_privacy,
            "scenes": scenes,
        }
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.settings.output_dir / "job.json", job)
        atomic_write_json(self.settings.output_dir / "pipeline-plan.json", {
            "scripts": scripts, "script": script, "metadata": metadata, "scenes": scenes, "job": job,
        })
        return job

    def run(self, *, dry_run: bool = False, no_upload: bool = False,
            script_id: str | None = None) -> dict[str, object]:
        job = self.reserve(script_id, persist=not dry_run)
        is_incident = job.get("content_type") == "documented_strange_incident"
        if is_incident:
            assert self.incidents is not None
            scripts = [self.incidents.get(str(job["script_id"]))]
        else:
            scripts = [self.bank.get(str(value)) for value in job.get("script_ids", [job["script_id"]])]
        script = scripts[0]
        plan = json.loads((self.settings.output_dir / "pipeline-plan.json").read_text(encoding="utf-8"))
        if dry_run:
            return {"status": "dry-run", "script_id": script["id"],
                    "script_ids": [item["id"] for item in scripts],
                    "plan": str(self.settings.output_dir / "pipeline-plan.json")}
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
                return {"status": "rendered", "script_id": script["id"],
                        "script_ids": [item["id"] for item in scripts], "video": str(video)}
            state["stage"] = "uploading"
            atomic_write_json(self.settings.state_path, state)
            result = upload_video(video, job, self.settings.root, self.settings.upload_privacy)
            video_id = str(result.get("youtube_video_id", ""))
            if not video_id:
                raise RuntimeError("YouTube upload returned no video ID")
            if is_incident:
                assert self.incidents is not None
                self.incidents.mark_used(str(script["id"]), video_id)
            else:
                self.bank.mark_used_many([str(item["id"]) for item in scripts], video_id)
            state.update({
                "stage": "complete", "pending_incident_id": None,
                "pending_script_id": None, "pending_script_ids": [], "pending_job_id": None,
                "last_success": {"script_id": script["id"], "script_ids": [item["id"] for item in scripts],
                                 "youtube_video_id": video_id, "completed_at": utc_now()},
            })
            atomic_write_json(self.settings.state_path, state)
            return result
        except Exception:
            # Intentionally preserve READY status and reservation for a safe retry.
            state["stage"] = "failed"
            state["failed_at"] = utc_now()
            atomic_write_json(self.settings.state_path, state)
            raise
