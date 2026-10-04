from __future__ import annotations

import os

import requests


def notify(message: str) -> bool:
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("Telegram not configured; notification skipped")
        return False
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message[:3900], "disable_web_page_preview": True}, timeout=20,
    )
    response.raise_for_status()
    return True
