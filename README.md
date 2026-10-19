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
- four daily quality-gated attempts at 05:00, 08:00, 11:00, and 14:00 Myanmar time; weak videos are skipped

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

Open **Actions → Create Reddit idol Short → Run workflow**. Choose an idol or leave it blank for rotation, choose 3 or 4 facts, and keep the default subreddit list. Set `dry_run` to download, score, render when eligible, and upload a quality report **without** publishing. A manual or scheduled run publishes only when the final quality gate passes. Blank-idol runs inspect up to 16 topics (starting with 10), metadata-filter them, render up to 6, and choose the highest quality/diversity score.

## Content Quality Pipeline v2

The existing downloader, Piper narration, captions, FFmpeg compositor, and YouTube uploader remain in place. Before editing, `scripts/content_quality.py` probes each candidate with ffprobe, rejects low-resolution/fps/duration sources, samples four frames for lightweight dHash duplicate checks, and calculates a 0–100 score from configurable source quality, engagement (when present), recency (when present), duration, uniqueness, and format. It ranks the passing clips and requires at least three distinct sources. Downloaded file hashes and frame hashes from the most recent 30 **published** videos are persisted in `data/reddit_state.json` only after a successful upload.

The pacing planner uses a short hook shot, variable early/middle/end shot lengths, forward-only offsets into each source, and a maximum 35% contribution from one source. It can try four deterministic edit orders (strongest visual, hook/body/payoff, comparison, timeline) while retaining the no-loop and source-share rules. If a rotating topic has only three distinct fact posts, a shorter source-backed video is allowed instead of padding footage. If footage is insufficient, it rejects the candidate and tries another idol. A final gate probes the rendered video, checks audio silence/level, black sections, caption timing/safe position, pacing, and technical integrity. Rejection is a successful workflow outcome with no YouTube upload, not a broken infrastructure run. Reports are saved as `quality_reports/<run-id>-<idol>.json` and uploaded as GitHub Actions artifacts, including when no video is published. GitHub Actions runs remain scheduled four times a day, but four uploads are no longer forced.

All tuning lives in [`config/content_quality.json`](config/content_quality.json). Defaults include 720×720 minimum source, 24fps, 3–180s source duration, minimum source score 60, final tiers A≥80/B≥72/C≥65 with an absolute 65 floor, 3–4 distinct sources, 1.5s hook maximum, 2.5s early maximum, 4s normal maximum, 6s absolute maximum, and a 35% per-source share limit. `quality_reports/daily_summary.json` counts actual YouTube uploads in the Myanmar calendar day. There are four daily scheduled slots, but four uploads cannot be guaranteed when fewer than four compliant videos exist or YouTube rejects an upload; the floor and duplicate checks are never relaxed. No AI/LLM API is called.

## Source safety

Reddit is used as a source signal, not independent verification. The generated metadata and YouTube description record the source URLs. Review factual claims and bundled-music rights before publication.

## Local validation

```powershell
pip install -r requirements.txt
pytest -q
python -m scripts.validate_config --mode reddit-short
```
