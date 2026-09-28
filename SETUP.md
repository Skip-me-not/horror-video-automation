# Setup

## 1. YouTube OAuth

Create a Google Cloud OAuth desktop client, enable YouTube Data API v3 (and YouTube Analytics API if wanted), then run:

```powershell
python tools/get_refresh_token.py path/to/client_secret.json
```

Add `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN` as GitHub Actions secrets. Tokens are never committed or printed by workflows. Existing upload-only refresh tokens continue to upload; analytics-only metrics may remain unavailable until reauthorization with read scopes.

No Gemini or other text-generation API key is needed. The local script generator uses verified feed claims and rejects scripts with fewer than 120 grounded words, unsupported numbers, or eight copied consecutive source words. If the available reporting is too sparse, that scheduled slot is skipped rather than inventing detail. Review output quality before enabling unattended public upload.

## 2. Telegram (optional)

Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Missing Telegram credentials do not make a validated render unsafe; the workflow logs that notifications were skipped.

## 2a. Reddit media discovery (optional, no automatic rights assumption)

Create a Reddit OAuth app and add `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` as Actions secrets. Set repository variable `REDDIT_USER_AGENT` to a distinct application-and-contact string. Discovery uses authenticated, spaced requests with bounded retry and a six-hour cache. Without OAuth credentials, original graphics are used.

Review `data/media_sources.json` after discovery. To approve an exact asset, add its `asset_id`, verified `original_source_url`, compatible `license`, `permission_evidence_url`, `approved_by`, and `approved_at` to `config/reddit_media_approvals.json`. Reddit hosting alone is never sufficient. High-risk posts remain rejected even with an approval entry. If your use of Reddit's API is commercial, obtain any separate authorization its [Data API terms](https://redditinc.com/policies/data-api-terms) require.

## 3. Publishing mode

The supplied workflow defaults to automatic public publication for verified stories. Before its first scheduled run, set repository variable `AUTO_PUBLISH=false` while inspecting dry-run previews and the channel's OAuth connection. Pending IDs are in `data/kpop_state.json` and `data/manifests/`; **Actions → Lululala Review and Publish** handles manual approvals.

For unattended publishing, set `AUTO_PUBLISH=true` and `UPLOAD_PRIVACY=public` as repository variables. Four cron triggers are upload attempts, not a guarantee of four qualifying stories. Topics that fail evidence, licensing, word-count, or video quality gates cannot upload.

## 4. Research sources

Edit `config/kpop.yaml`. Each feed needs a name, feed URL, kind, reliability score, and `rights: facts_only`. A source grants permission to summarize facts—not to reuse its photographs or video.

## 5. Optional approved media

Place user-owned/public-domain/explicitly licensed files under `assets/approved/` and add complete license metadata to `assets/approved/manifest.json`. Invalid or missing records fail closed. With no approved Reddit media, original motion graphics are used. `assets/music/README.md` documents the original soundtrack synthesized locally during each run.

## 6. Manual test

Run **Lululala Manual Dry Run** first. Inspect its MP4, manifest, quality report, transcript, captions, and cover artifact before enabling any upload.

For a guaranteed non-publishing local integration render:

```powershell
python src/celebrity_main.py --dry-run --story-limit 1 --fixture tests/fixtures/verified_topic.json
```

For live news/media discovery without upload:

```powershell
python src/celebrity_main.py --dry-run --story-limit 1
```

Publishing is orchestrated by **Lululala Korean Celebrity News Production** in GitHub Actions; a local `produce` command only creates a candidate and never calls the YouTube API by itself.

## Required secrets

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`
- `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` (optional; required for Reddit discovery)
- `TELEGRAM_BOT_TOKEN` (optional)
- `TELEGRAM_CHAT_ID` (optional)
- `AUTO_PUBLISH` repository variable (optional; workflow defaults true)

## Repository variable

- `UPLOAD_PRIVACY` — `private`, `unlisted`, or `public`; production workflow defaults to `public`.
- `REDDIT_USER_AGENT` — descriptive OAuth client user agent, required with Reddit credentials.
