from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import requests

from .parser import parse_short

ROOT = Path(__file__).resolve().parents[1]


def _allowed(raw: str) -> set[int]:
    try:
        return {int(part.strip()) for part in raw.split(",") if part.strip()}
    except ValueError as exc:
        raise ValueError("Telegram allowlists must contain numeric IDs") from exc


def authorize(user_id: int, chat_id: int) -> bool:
    users = _allowed(os.getenv("ALLOWED_TELEGRAM_USER_IDS", ""))
    chats = _allowed(os.getenv("ALLOWED_TELEGRAM_CHAT_IDS", ""))
    return bool(users or chats) and (not users or user_id in users) and (not chats or chat_id in chats)


def dispatch(job: dict, chat_id: int, *, session: requests.Session | None = None) -> None:
    repo = os.getenv("GITHUB_REPOSITORY", "Skip-me-not/horror-video-automation")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid GITHUB_REPOSITORY")
    token = os.getenv("GH_PAT", "")
    if not token:
        raise RuntimeError("GH_PAT is not configured")
    body = {"event_type": "render_short", "client_payload": {"job": job, "chat_id": chat_id}}
    if len(json.dumps(body, ensure_ascii=False).encode("utf-8")) >= 60_000:
        raise ValueError("job is too large for repository_dispatch")
    key = job["dedupe_key"]
    client = session or requests.Session()
    for folder in ("completed", "locks"):
        response = client.get(
            f"https://api.github.com/repos/{repo}/contents/jobs/{folder}/{key}.json",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=20,
        )
        if response.status_code == 200:
            raise ValueError("this PERSON + SCRIPT was already submitted; set FORCE:true to submit again")
        if response.status_code != 404:
            response.raise_for_status()
    response = client.post(
        f"https://api.github.com/repos/{repo}/dispatches",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json=body, timeout=20,
    )
    if response.status_code != 204:
        response.raise_for_status()


def _store(job: dict, folder: str) -> Path:
    target = ROOT / "jobs" / folder / f"{job['job_id']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def sync_local_jobs(*, session: requests.Session | None = None) -> int:
    """Move bot-host JSONs when the corresponding Actions run finishes."""
    pending = ROOT / "jobs" / "pending"
    files = list(pending.glob("*.json")) if pending.is_dir() else []
    if not files:
        return 0
    repo = os.getenv("GITHUB_REPOSITORY", "Skip-me-not/horror-video-automation")
    token = os.getenv("GH_PAT", "")
    if not token:
        return 0
    response = (session or requests.Session()).get(
        f"https://api.github.com/repos/{repo}/actions/workflows/render-short.yml/runs",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        params={"per_page": 100}, timeout=20,
    )
    response.raise_for_status()
    runs = {str(item.get("display_title", "")): item for item in response.json().get("workflow_runs", [])}
    moved = 0
    for path in files:
        run = runs.get(f"Telegram Short {path.stem}")
        if not run or run.get("status") != "completed":
            continue
        folder = "private_completed" if run.get("conclusion") == "success" else "failed"
        destination = ROOT / "jobs" / folder / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        path.replace(destination)
        moved += 1
    return moved


async def _sync_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(sync_local_jobs)
        except Exception:
            pass
        await asyncio.sleep(60)


async def _on_start(application) -> None:
    application.create_task(_sync_loop())


async def _short(update, context) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return
    if not authorize(user.id, chat.id):
        await message.reply_text("Unauthorized.")
        return
    try:
        job = parse_short(message.text or "")
        pending = _store(job, "pending")
        try:
            await asyncio.to_thread(dispatch, job, chat.id)
        except Exception:
            failed = ROOT / "jobs" / "failed" / pending.name
            failed.parent.mkdir(parents=True, exist_ok=True)
            pending.replace(failed)
            raise
        await message.reply_text(f"🎬 Job accepted\nJob ID: {job['job_id']}\nGitHub Actions will send render/upload status here.")
    except (ValueError, RuntimeError, requests.RequestException) as exc:
        await message.reply_text(f"❌ Request rejected: {str(exc)[:350]}")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    if not (_allowed(os.getenv("ALLOWED_TELEGRAM_USER_IDS", "")) or
            _allowed(os.getenv("ALLOWED_TELEGRAM_CHAT_IDS", ""))):
        raise SystemExit("configure at least one Telegram user/chat allowlist")
    from telegram.ext import Application, CommandHandler

    app = Application.builder().token(token).post_init(_on_start).build()
    app.add_handler(CommandHandler("short", _short))
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
