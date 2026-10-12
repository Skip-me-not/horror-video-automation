# Setup: AI-written Reddit idol Shorts

## Prerequisites

- GitHub Actions enabled
- YouTube OAuth upload credentials
- Openverse API credentials for CC0/Public Domain music
- No Reddit client credentials are needed

Do not commit OAuth files, tokens, or API secrets.

## GitHub secrets and variables

Under **Settings → Secrets and variables → Actions**, add:

| Name | Type |
|---|---|
| `OPENVERSE_CLIENT_ID` | Secret |
| `OPENVERSE_CLIENT_SECRET` | Secret |
| `YOUTUBE_CLIENT_ID` | Secret |
| `YOUTUBE_CLIENT_SECRET` | Secret |
| `YOUTUBE_REFRESH_TOKEN` | Secret |
| `CHANNEL_NAME` | Variable |
| `REDDIT_USER_AGENT` | Optional variable |

The workflow uses the built-in `GITHUB_TOKEN` with `models: read` for the GitHub Models rewrite. It does not require `REDDIT_CLIENT_ID` or `REDDIT_CLIENT_SECRET`.

## Manual run

Open **Actions → Create AI-written Reddit idol Short → Run workflow**.

- `idol`: enter an idol or leave blank for rotation
- `fact_count`: choose 3 or 4
- `subreddits`: general communities; the source layer also adds a mapped fan community
- `ai_script_mode`: `auto` is recommended; `required` fails if GitHub Models is unavailable; `fallback` is deterministic and does not call a model

Every successful run uploads as **public**. The four scheduled runs also upload as public.

## What the AI receives

The model receives normalized Reddit signals only: source ID, title, subreddit, score, and comment count. It is instructed to rewrite those signals into spoken commentary and never invent dates, numbers, quotes, or achievements. The raw Reddit title is not used as the complete narration beat.

If the model call fails in `auto`, the renderer uses a source-grounded editorial fallback and records `script_engine: editorial_fallback` in `output/metadata.json`. In a successful model run it records `script_engine: github_models` and the model name.

## Caption and visual treatment

The renderer creates one timed ASS event per spoken word. Captions use the bundled Poppins font, hot pink fill, a heavy black outline, yellow emphasis for numbers/highlight terms, and red emphasis for warning words. The caption sits at approximately `y=1120` inside the 1080×1920 safe area. Clips are cut about every 4.6 seconds with blurred background fill behind the centered source video.

## Rights and accuracy

Reddit hosting is not a reuse license. Source URLs are recorded for audit, but public publication still requires the operator to review permissions and claims. The AI prompt reduces invention risk; it does not independently verify Reddit claims.

## Local checks

```powershell
pip install -r requirements.txt
pytest -q
python -m scripts.validate_config --mode reddit-ai
```

A real render additionally needs FFmpeg, the cached Piper voice, network access, and the configured YouTube/Openverse credentials.
