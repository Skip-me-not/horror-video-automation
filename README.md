# Lululala Korean Celebrity News Shorts

A GitHub Actions pipeline for English Korean-celebrity, K-drama, and K-pop news Shorts. It collects publisher RSS, groups similar headlines, scores and verifies stories, synthesizes English narration, renders original 1080×1920 graphics, checks the MP4, and uses the official YouTube Data API.

## Safety defaults

- Automatic public publishing is configured only when `GEMINI_API_KEY` is present and a source-grounded rewrite passes validation. Without the key, the workflow can preview but will not auto-publish. Set repository variable `AUTO_PUBLISH=false` to disable publication entirely.
- Upload approval is two-phase: private upload → durable video-ID record → requested visibility.
- No Reddit/TikTok/YouTube performance clip is downloaded by the active workflows.
- Public availability is never treated as a reuse license.
- Rumors, dating speculation, private-life claims, and weakly sourced breaking news are rejected or queued for review.
- Missing corroboration or insufficient material for a 120-word script means no video is published for that slot. Four scheduled runs do not guarantee four uploads.
- Public feed access does not authorize reuse of article text, celebrity photos, or television footage. The rewrite rejects long verbatim passages and unsupported numbers, but automated fact checks are imperfect; review previews before enabling unattended public publication.

## Content formats

The configurable allocation covers eight editorial formats. State tracks article IDs, event topics, entities, hooks, slots, pending items, upload IDs, and analytics snapshots. Latest RSS records and ranked topics are saved in `data/news.json`, `data/unique_news.json`, and `data/verified_topics.json`; confirmed uploads are in `data/upload_history.json`.

## Schedule

`kpop-production.yml` targets 07:00, 12:00, 15:00, and 19:00 Asia/Yangon (00:30, 05:30, 08:30, and 12:30 UTC). GitHub may delay scheduled jobs. `kpop-catch-up.yml` can dispatch one elapsed missing slot without duplicating a completed slot.

## Workflows

- `kpop-production.yml` — four scheduled/manual research, script, render, validation, slot reservation, and verified public upload attempts.
- `kpop-dry-run.yml` — non-publishing fixture or live-research render.
- `kpop-approval.yml` — approve/reject and select private, unlisted, or public visibility.
- `kpop-recovery.yml` — idempotent recovery of a failed slot.
- `kpop-catch-up.yml` — optional single-slot catch-up.
- `kpop-analytics.yml` and `kpop-weekly-report.yml` — official API reports; unavailable metrics remain explicitly unavailable.
- `tests.yml` — unit tests and a playable FFmpeg integration render.

## Quick local dry run

```powershell
python -m pip install -r requirements.txt pytest
python -m pytest -q
python -m src.kpop_automation.cli produce --dry-run --slot local-test --fixture tests/fixtures/verified_topic.json
ffprobe output/short.mp4
```

The fixture is fictional, marked non-publishable, and cannot be used without `--dry-run`.

The renderer writes `output/scripts/`, `output/audio/`, and `output/videos/` alongside its compatibility files. Production media remains ignored by Git and is removed from the Actions runner after the job; preview artifacts expire automatically. Feed failures are logged and other feeds continue.

See [SETUP.md](SETUP.md) and [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
