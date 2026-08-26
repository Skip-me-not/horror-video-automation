from __future__ import annotations

from typing import Any


def generate_metadata(game: dict[str, Any], privacy: str = "private") -> dict[str, Any]:
    titles = {
        "choose_door": "Only One Door Is Safe 😨",
        "find_ghost": "Can You Find the Ghost? 👻",
        "spot_change": "What Changed in This Room?",
        "escape_room": "Where Would You Hide? 😰",
        "safe_object": "One of These Is Cursed",
        "moving_entity": "Which Entity Moved?",
    }
    return {
        "title": titles[game["game_type"]],
        "description": "Did you survive? Watch again and check your answer.\n\n#horror #interactive #scary #shorts",
        "tags": ["horror", "interactive", "scary", "shorts"],
        "category_id": "24",
        "privacy_status": privacy,
    }
