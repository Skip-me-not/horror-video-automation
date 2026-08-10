"""Dependency-light smoke check for the dynamic Shorts pipeline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_job_from_idea import build_job
from scripts.common import desired_background_scenes, effective_video_duration, load_config
from scripts.fetch_background import provider_order, select_pixabay_video, select_video_file
from scripts.generate_idea_bank import build_ideas
from scripts.validate_job import validate_job


def main() -> None:
    config = load_config("config/default.json")
    ideas = build_ideas()
    assert len(ideas) == 180
    assert len({idea["genre"] for idea in ideas}) == 15
    assert len({idea["title"] for idea in ideas}) == len(ideas)
    assert len({idea["story"] for idea in ideas}) == len(ideas)
    for idea in ideas:
        validate_job(build_job(idea, f"idea-{idea['idea_number']:03d}"), config)
    short = effective_video_duration(25, config, "short")
    long = effective_video_duration(95, config, "long")
    assert short < long
    assert desired_background_scenes(short, config) < desired_background_scenes(long, config)
    assert set(provider_order("job", 0, "pexels", "pixabay")) == {
        "pexels", "pixabay", "wikimedia", "archive",
    }
    pexels, _ = select_video_file({"videos": [{
        "id": 7, "video_files": [{"file_type": "video/mp4", "width": 1080,
        "height": 1920, "link": "https://player.vimeo.com/example.mp4"}],
    }]}, "job")
    assert pexels["id"] == 7
    pixabay, _ = select_pixabay_video({"hits": [{
        "id": 8, "videos": {"medium": {"width": 1920, "height": 1080,
        "size": 1000, "url": "https://cdn.pixabay.com/video/example.mp4"}},
    }]}, "job")
    assert pixabay["id"] == 8
    print(
        f"validated={len(ideas)} duration={short}/{long} "
        f"scenes={desired_background_scenes(short, config)}/{desired_background_scenes(long, config)}"
    )


if __name__ == "__main__":
    main()
