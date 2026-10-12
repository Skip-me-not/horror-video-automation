# Setup: deterministic Reddit idol Shorts

## GitHub settings

Under **Settings → Secrets and variables → Actions**, configure:

| Name | Type |
|---|---|
| `YOUTUBE_CLIENT_ID` | Secret |
| `YOUTUBE_CLIENT_SECRET` | Secret |
| `YOUTUBE_REFRESH_TOKEN` | Secret |
| `CHANNEL_NAME` | Variable |
| `REDDIT_USER_AGENT` | Optional variable |

This version does not use AI, OpenCode, OpenVerse, Reddit client credentials, or an external music API. Music comes from the bundled `music/` directory.

## Run

Open **Actions → Create Reddit idol Short → Run workflow**. Select an idol, choose `3` or `4` source-backed beats, and leave the subreddit list at its default unless you want a different public community set.

Scheduled and manual runs upload as public. The workflow renders with local Piper TTS and uses deterministic source-grounded editorial copy. It does not send source data to an AI provider.

## Rights and accuracy

Reddit popularity is not fact verification, and Reddit hosting is not a reuse license. Source URLs are retained in `output/metadata.json` and the YouTube description. Review claims, clip permissions, and bundled music rights before publication.

## Local checks

```powershell
pip install -r requirements.txt
pytest -q
python -m scripts.validate_config --mode reddit-short
```
