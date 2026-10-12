# AI-written Reddit idol Shorts

This project creates public 55–65 second vertical YouTube Shorts about K-pop idols. Reddit is used to discover source signals and hosted clips; the narration is rewritten into original commentary by GitHub Models when available.

## Format

- 1080×1920, 30 fps, H.264/AAC
- three or four source-backed story beats per Short
- AI-written hook, fact commentary, and CTA rather than reading Reddit post titles verbatim
- one-word-at-a-time Poppins captions inspired by the supplied reference: hot pink, black outline, yellow/red emphasis, lower-middle safe area
- a visual treatment about every 4.6 seconds with blurred vertical fill for non-9:16 clips
- local Piper narration and low-volume CC0/Public Domain Openverse music
- direct public YouTube upload four times daily at 05:00, 08:00, 11:00, and 14:00 Myanmar time

## Source and AI behavior

`data/idols.json` controls the idol rotation. Public Reddit fetching is credential-free and uses JSON/RSS/Old Reddit/archive fallbacks. Reddit client secrets are not required.

`scripts/ai_script.py` sends only normalized source signals—title, subreddit, score, and comment count—to the configured GitHub Models endpoint. The prompt explicitly forbids inventing facts and requires JSON with a hook, exactly three or four fact beats, and a CTA. The renderer stores `script_engine`, `script_model`, and `script_prompt_version` in `output/metadata.json`.

`AI_SCRIPT_MODE=auto` uses GitHub Models when the workflow token is accepted and falls back to source-grounded editorial commentary if the model is unavailable. `required` fails instead of falling back. `fallback` never calls a model and is useful for local smoke tests.

Reddit popularity is a source signal, not factual verification. Every selected fact and clip permalink is recorded in metadata and the YouTube description. The operator remains responsible for copyright permission, attribution, fact checking, and YouTube policy compliance.

## GitHub Actions

The active workflow is `.github/workflows/create-short.yml`.

Required repository secrets:

- `OPENVERSE_CLIENT_ID`
- `OPENVERSE_CLIENT_SECRET`
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Required repository variable:

- `CHANNEL_NAME`

Optional repository variable:

- `REDDIT_USER_AGENT`

The workflow grants `models: read` to the built-in GitHub token and uses `https://models.github.ai/inference/chat/completions` with `openai/gpt-4o-mini`. No Reddit client ID or secret is used.

## Files

- `scripts/ai_script.py` — structured AI rewrite and safe fallback
- `scripts/reddit_source.py` — credential-free Reddit discovery and filtering
- `scripts/render_idol_short.py` — narration, reference-style captions, clip recovery, FFmpeg render, and metadata
- `scripts/merge_reddit_state.py` — conflict-safe source rotation
- `data/reddit_state.json` — previously used sources and idols

## Validation

```bash
pip install -r requirements.txt
pytest -q
python -m scripts.validate_config --mode reddit-ai
```

The tests do not upload to YouTube or call Reddit. The full Actions run performs the network discovery, AI rewrite, render, public upload, and state persistence.
