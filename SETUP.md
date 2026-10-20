# Setup: deterministic Reddit idol Shorts

## GitHub settings

Under **Settings → Secrets and variables → Actions**, configure:

| Name | Type |
|---|---|
| `YOUTUBE_CLIENT_ID` | Secret |
| `YOUTUBE_CLIENT_SECRET` | Secret |
| `YOUTUBE_REFRESH_TOKEN` | Secret |
| `CHANNEL_NAME` | Optional variable; defaults to `Lululala` |
| `REDDIT_USER_AGENT` | Optional variable |

This version does not use AI, OpenCode, OpenVerse, Reddit client credentials, or an external music API. Music comes from the bundled `music/` directory.

## Run

Open **Actions → Create Reddit idol Short → Run workflow**. Select an idol, choose `3` or `4` source-backed beats, and leave the subreddit list at its default unless you want a different public community set. Set `dry_run` to render and inspect an artifact without uploading.

Scheduled runs and manual runs without `dry_run` upload as public. Four primary daily slots search up to 16 topics and render up to 10 candidates. Each slot has a retry 40 minutes later; the retry reads the persisted daily YouTube IDs and exits when that slot is already filled. If the normal pool is exhausted, quota backfill may reuse older source posts and use the configured 45/55 source/final score thresholds, while technical corruption and within-video duplicates remain blocked. `quality_reports/daily_summary.json` records discovered/analyzed/rendered/published counts, tiers, and actual YouTube IDs. The workflow uses local Piper TTS and does not send source data to an AI provider.

## Rights and accuracy

Reddit popularity is not fact verification, and Reddit hosting is not a reuse license. Source URLs are retained in `output/metadata.json` and the YouTube description. Review claims, clip permissions, and bundled music rights before publication.

## Local checks

```powershell
pip install -r requirements.txt
pytest -q
python -m scripts.validate_config --mode reddit-short
```
