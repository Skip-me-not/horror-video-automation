from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    from google_auth_oauthlib.flow import InstalledAppFlow
    parser = argparse.ArgumentParser(description="Authorize YouTube once and print a refresh token")
    parser.add_argument("client_secret", type=Path, help="OAuth desktop client JSON downloaded from Google Cloud")
    args = parser.parse_args()
    client = json.loads(args.client_secret.read_text(encoding="utf-8"))
    flow = InstalledAppFlow.from_client_config(client, ["https://www.googleapis.com/auth/youtube.upload"])
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    print("\nAdd these values as GitHub Actions secrets:")
    print(f"YOUTUBE_CLIENT_ID={credentials.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={credentials.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
