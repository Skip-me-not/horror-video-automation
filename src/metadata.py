from __future__ import annotations

from typing import Any


def generate_metadata(game: dict[str, Any], privacy: str = "private") -> dict[str, Any]:
    titles = {
        "choose_door": "Choose a Door Before the Light Dies 😨",
        "find_ghost": "Find the Hidden Face Before Time Runs Out",
        "spot_change": "Something Changed. Can You See It?",
        "escape_room": "You Have 5 Seconds to Find a Hiding Place",
        "safe_object": "Pick One Object. The Others Are Cursed.",
        "moving_entity": "One Entity Moved. Which One?",
    }
    prompts = {
        "choose_door": "A or B? Comment your first choice before replaying.",
        "find_ghost": "Where did you see it? Comment before replaying.",
        "spot_change": "What changed? Lock your answer before replaying.",
        "escape_room": "Where would you hide? Comment your first choice.",
        "safe_object": "Which object did you trust? Comment your choice.",
        "moving_entity": "01, 02, or 03? Comment before replaying.",
    }
    return {
        "title": titles[game["game_type"]],
        "description": f"{prompts[game['game_type']]}\n\n#horror #interactive #scary #shorts",
        "tags": ["horror", "interactive", "scary", "shorts"],
        "category_id": "24",
        "privacy_status": privacy,
    }
