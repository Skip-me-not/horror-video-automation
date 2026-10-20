# Deterministic Reddit idol Shorts

This repository creates public 55–65 second K-pop idol Shorts from public Reddit source signals and Reddit-hosted clips. It does **not** call an AI model, OpenCode, OpenVerse, or any Reddit credentialed API.

## Output

- 1080×1920 H.264/AAC at 30fps
- three or four source-backed beats
- deterministic editorial rewriting from the source titles and engagement signals
- one-word hot-pink captions with black outline and yellow/red emphasis
- blurred vertical fill and variable, source-aware cuts (fastest in the opening)
- local Piper narration
- bundled repository music selected locally
- four daily public-upload slots at 05:00, 08:00, 11:00, and 14:00 Myanmar time, each with a guarded retry 40 minutes later

## Required GitHub configuration

Secrets:

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Optional variable (defaults to `Lululala`):

- `CHANNEL_NAME`

Optional variable:

- `REDDIT_USER_AGENT`

No `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `OPENVERSE_CLIENT_ID`, `OPENVERSE_CLIENT_SECRET`, AI key, or OpenCode key is required.

## Manual run

Open **Actions → Create Reddit idol Short → Run workflow**. Choose an idol or leave it blank for rotation, choose 3 or 4 facts, and keep the default subreddit list. Set `dry_run` to download, score, render when eligible, and upload a quality report **without** publishing. Blank-idol runs inspect all 16 configured topics, metadata-filter them, render up to 10, and choose the highest quality/diversity score.

## Content Quality Pipeline v2

The existing downloader, Piper narration, captions, FFmpeg compositor, and YouTube uploader remain in place. Before editing, `scripts/content_quality.py` probes each candidate with ffprobe, rejects low-resolution/fps/duration sources, samples four frames for lightweight dHash duplicate checks, and calculates a 0–100 score from configurable source quality, engagement (when present), recency (when present), duration, uniqueness, and format. It ranks the passing clips and requires at least three distinct sources. Downloaded file hashes and frame hashes from the most recent 30 **published** videos are persisted in `data/reddit_state.json` only after a successful upload.

The pacing planner uses a short hook shot, variable early/middle/end shot lengths, forward-only offsets into each source, and a maximum 35% contribution from one source. It can try four deterministic edit orders (strongest visual, hook/body/payoff, comparison, timeline) while retaining the no-loop and technical-integrity rules. If a rotating topic has only three distinct fact posts, a shorter source-backed video is allowed instead of padding footage. The daily-quota fallback may reuse an older source and lower source/final scoring thresholds to 45/55 only after the normal pool is exhausted; corrupted media, undecodable footage, invalid audio, bad aspect ratio, long black sections, and within-video duplicates still fail. Reports explicitly mark `quota_backfill`.

All tuning lives in [`config/content_quality.json`](config/content_quality.json). Normal tiers remain A≥80/B≥72/C≥65. `quality_reports/daily_summary.json` counts actual YouTube uploads in the Myanmar calendar day. Each retry checks its slot target before rendering, so a successful primary run is not duplicated. The system targets exactly four daily uploads; YouTube/API outages, account quota exhaustion, or GitHub failing to start a scheduled job remain external failure cases. No AI/LLM API is called.

## Source safety

Reddit is used as a source signal, not independent verification. The generated metadata and YouTube description record the source URLs. Review factual claims and bundled-music rights before publication.

## Local validation

```powershell
pip install -r requirements.txt
pytest -q
python -m scripts.validate_config --mode reddit-short
```
