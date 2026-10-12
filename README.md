# Deterministic Reddit idol Shorts

This repository creates public 55–65 second K-pop idol Shorts from public Reddit source signals and Reddit-hosted clips. It does **not** call an AI model, OpenCode, OpenVerse, or any Reddit credentialed API.

## Output

- 1080×1920 H.264/AAC at 30fps
- three or four source-backed beats
- deterministic editorial rewriting from the source titles and engagement signals
- one-word hot-pink captions with black outline and yellow/red emphasis
- blurred vertical fill and approximately 4.6-second cuts
- local Piper narration
- bundled repository music selected locally
- public YouTube upload four times daily at 05:00, 08:00, 11:00, and 14:00 Myanmar time

## Required GitHub configuration

Secrets:

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Variable:

- `CHANNEL_NAME`

Optional variable:

- `REDDIT_USER_AGENT`

No `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `OPENVERSE_CLIENT_ID`, `OPENVERSE_CLIENT_SECRET`, AI key, or OpenCode key is required.

## Manual run

Open **Actions → Create Reddit idol Short → Run workflow**. Choose an idol or leave it blank for rotation, choose 3 or 4 facts, and keep the default subreddit list. Every successful run publishes publicly.

## Source safety

Reddit is used as a source signal, not independent verification. The generated metadata and YouTube description record the source URLs. Review factual claims and bundled-music rights before publication.

## Local validation

```powershell
pip install -r requirements.txt
pytest -q
python -m scripts.validate_config --mode reddit-short
```
