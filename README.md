# Lululala Korean Celebrity News Shorts

A GitHub Actions pipeline for English Korean-celebrity, K-drama, and K-pop news Shorts. It collects publisher RSS, groups similar headlines, scores and verifies stories, discovers relevant Reddit media through OAuth, tracks media permissions, synthesizes English narration, renders 1080×1920 edits, checks the MP4, and uses the official YouTube Data API.

## Safety defaults

- No Gemini or other text-generation API key is needed. Scripts use deterministic source summaries. Publication requires 120–150 words, no unsupported numbers, no eight-word source copy, a verified topic, and passing video checks. Sparse feed summaries are skipped rather than padded with invented facts. Set repository variable `AUTO_PUBLISH=false` to disable publication entirely.
- Upload approval is two-phase: private upload → durable video-ID record → requested visibility.
- TikTok and YouTube performance clips are not downloaded. Reddit media is downloaded only with exact, documented reuse approval.
- Public availability is never treated as a reuse license.
- Rumors, dating speculation, private-life claims, and weakly sourced breaking news are rejected or queued for review.
- Missing corroboration or insufficient material for a 120-word script means no video is published for that slot. Four scheduled runs do not guarantee four uploads.
- A live feed smoke test on 2026-09-29 found 14 verified candidate topics but none with enough distinct, original source-backed material for the required 120–150-word no-API narration. Expect skipped slots until richer source data or editorially prepared scripts are available.
- Public feed access does not authorize reuse of article text, celebrity photos, or television footage. The script gate rejects long verbatim passages and unsupported numbers, but automated checks cannot establish factual accuracy or copyright permission; review previews before enabling unattended public publication.
- Reddit is a discovery source, not a license. Unknown-source, high-risk, or unapproved assets are recorded but never downloaded for production. Original motion graphics remain the fallback.

## Content formats

The configurable allocation covers eight editorial formats. State tracks article IDs, event topics, entities, hooks, slots, pending items, upload IDs, and analytics snapshots. Latest RSS records and ranked topics are saved in `data/news.json`, `data/unique_news.json`, and `data/verified_topics.json`; Reddit candidates and permission details are in `data/media_sources.json`; confirmed uploads are in `data/upload_history.json`.

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
python src/celebrity_main.py --dry-run --story-limit 1 --slot local-test --fixture tests/fixtures/verified_topic.json
ffprobe output/short.mp4
```

The fixture is fictional, marked non-publishable, and cannot be used without `--dry-run`.

The renderer writes `output/scripts/`, `output/audio/`, `output/media/`, `output/manifests/`, and `output/videos/` alongside compatibility files. It uses face-aware Pillow/OpenCV framing for approved images, short muted excerpts for approved clips, original generated ambience, burned captions, and a source-linked timeline manifest. Production media remains ignored by Git and is removed from the Actions runner after the job; preview artifacts expire automatically. Feed failures are logged and other feeds continue.

## Reddit rights gate

Set `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and a descriptive `REDDIT_USER_AGENT` before live discovery. A discovered post appears in `data/media_sources.json` with `approved_for_use: false` by default. Add a matching, evidence-backed entry to `config/reddit_media_approvals.json` only when the original source and reuse permission are verified. Accepted bases are CC0, CC BY 4.0, public domain, ownership, or explicit permission. Automatic editing is not a substitute for permission. Reddit's [Data API terms](https://redditinc.com/policies/data-api-terms) may require a separate agreement for commercial use; check your intended channel use.

See [SETUP.md](SETUP.md) and [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
