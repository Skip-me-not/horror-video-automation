from __future__ import annotations

from typing import Any


def generate_metadata(game: dict[str, Any], privacy: str = "private") -> dict[str, Any]:
    return {
        "title": "Can You Survive All 5 Horror Rooms?",
        "description": "Which stage defeated you—1, 2, 3, 4, or 5? Comment before replaying.\n\n#horror #interactive #scary #shorts",
        "tags": ["horror", "interactive", "scary", "shorts"],
        "category_id": "24",
        "privacy_status": privacy,
    }
