from __future__ import annotations

import argparse
import os

import requests


def send(text: str, chat_id: str | int) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token or not str(chat_id):
        return
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": str(chat_id), "text": text[:3900], "disable_web_page_preview": True},
        timeout=20,
    )
    response.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-id", default=os.getenv("TELEGRAM_CHAT_ID", ""))
    parser.add_argument("--text", required=True)
    args = parser.parse_args()
    send(args.text, args.chat_id)


if __name__ == "__main__":
    main()
