# Setup

## 1. YouTube OAuth

Create a Google Cloud OAuth desktop client, enable YouTube Data API v3 (and YouTube Analytics API if wanted), then run:

```powershell
python tools/get_refresh_token.py path/to/client_secret.json
```

Add `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN` as GitHub Actions secrets. Tokens are never committed or printed by workflows. Existing upload-only refresh tokens continue to upload; analytics-only metrics may remain unavailable until reauthorization with read scopes.

Create a Gemini API key in Google AI Studio and add `GEMINI_API_KEY` as another Actions secret. The pipeline requires a source-grounded rewrite that passes word-count, source-overlap, and number checks before unattended public upload. Without this key it can make deterministic previews, but will not auto-publish. Gemini 2.5 Flash has a free API tier subject to regional availability and quota; use a free-tier project if zero cost is required.

## 2. Telegram (optional)

Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Missing Telegram credentials do not make a validated render unsafe; the workflow logs that notifications were skipped.

## 3. Publishing mode

The supplied workflow defaults to automatic public publication for verified stories. Before its first scheduled run, set repository variable `AUTO_PUBLISH=false` while inspecting dry-run previews and the channel's OAuth connection. Pending IDs are in `data/kpop_state.json` and `data/manifests/`; **Actions → Lululala Review and Publish** handles manual approvals.

For unattended publishing, set `AUTO_PUBLISH=true` and `UPLOAD_PRIVACY=public` as repository variables. Four cron triggers are upload attempts, not a guarantee of four qualifying stories. Topics that fail evidence, licensing, word-count, or video quality gates cannot upload.

## 4. Research sources

Edit `config/kpop.yaml`. Each feed needs a name, feed URL, kind, reliability score, and `rights: facts_only`. A source grants permission to summarize facts—not to reuse its photographs or video.

## 5. Optional approved media

Place user-owned/public-domain/explicitly licensed files under `assets/approved/` and add complete license metadata to `assets/approved/manifest.json`. Invalid or missing records fail closed. With no approved media, original motion graphics are used.

## 6. Manual test

Run **Lululala Manual Dry Run** first. Inspect its MP4, manifest, quality report, transcript, captions, and cover artifact before enabling any upload.

## Required secrets

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`
- `GEMINI_API_KEY` (required for unattended public uploads)
- `TELEGRAM_BOT_TOKEN` (optional)
- `TELEGRAM_CHAT_ID` (optional)
- `AUTO_PUBLISH` repository variable (optional; workflow defaults true)

## Repository variable

- `UPLOAD_PRIVACY` — `private`, `unlisted`, or `public`; production workflow defaults to `public`.
