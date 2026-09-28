# Telegram-requested YouTube Shorts

This is a separate, user-scripted workflow alongside the existing scheduled Lululala jobs. It does not invent a script or call a paid text-generation API. A Telegram message supplies the person, full narration and optional edit choices. The bot must run continuously on your computer or another always-on machine; GitHub Actions runs only after a job is dispatched. The workflow must be merged into the repository's default branch before `repository_dispatch` can trigger it.

## 1. Repository and YouTube

Install Python 3.11+ and FFmpeg/ffprobe. Run `python -m pip install -r requirements.txt`. The repository already uses `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` and `YOUTUBE_REFRESH_TOKEN` Actions secrets for YouTube uploads. If setting up a new channel, enable YouTube Data API v3, create OAuth credentials and use `python tools/get_refresh_token.py path/to/client_secret.json`. Uploads always start **private**; after the confirmed video ID is recorded, the workflow applies the job's requested `PRIVACY` (private by default).

## 2. Telegram and GitHub credentials

Create a bot in Telegram with BotFather. Store `TELEGRAM_BOT_TOKEN` both on the bot host and as an Actions secret for status messages. Put your numeric Telegram user ID in `ALLOWED_TELEGRAM_USER_IDS` and/or your private chat ID in `ALLOWED_TELEGRAM_CHAT_IDS` on the bot host. If both are set, both must match. Set `TELEGRAM_CHAT_ID` as an Actions secret for manual workflow notifications; repository dispatch instead carries the actual authorized chat ID.

Create a fine-grained GitHub token restricted to `Skip-me-not/horror-video-automation` with **Contents: read/write** (required by GitHub's repository-dispatch endpoint) and **Actions: read** (for local job-status synchronization). Set it as `GH_PAT` on the bot host, not in the repository. Set `GITHUB_REPOSITORY=Skip-me-not/horror-video-automation`. A successful dispatch returns HTTP 204. The bot checks existing completion/reservation receipts first. Keep tokens in environment variables or your OS secret store; never commit `.env` or send them in Telegram.

Start the long-polling bot from the repository root:

```powershell
python -m bot.telegram_bot
```

The bot stops receiving requests when that process/computer is offline. GitHub Actions is not a free always-on Telegram bot host.

## 3. Send a job

Send one message to the bot:

```text
/short
PERSON: Jennie BLACKPINK
TITLE: Jennie — Your Exact Title
SCRIPT: Paste your entire original narration here. The first sentence becomes the visual hook. Continue with all the words you want the voice to say.
STYLE: fast_celeb
VOICE: en-US-AriaNeural
DURATION: automatic
MEDIA: automatic
UPLOAD: youtube
PRIVACY: private
```

`PERSON` and `SCRIPT` are required. The parser also recognizes Burmese field labels such as `နာမည်:` and `စာသား:`. Use `VOICE: my-MM-NilarNeural` for Burmese voice if desired; Burmese fonts are installed in the GitHub runner. `DURATION` can be automatic or 10–180 seconds. A requested duration may speed up or slow down the voice modestly; a large mismatch fails rather than cutting narration. `UPLOAD: none` renders without YouTube. `PRIVACY` accepts private, unlisted or public. `FORCE: true` deliberately bypasses a previous content-hash receipt.

The user-supplied title is sent to YouTube exactly as entered, subject only to YouTube's 100-character limit checked at intake. If title is omitted, the neutral fallback is `PERSON — Latest Short Update`. The first sentence or up to ten initial words of `SCRIPT` appears as the hook; no new factual claim is generated.

## 4. Media and permission

`MEDIA: automatic` searches the approved local asset manifest. Wikimedia Commons discovery can be enabled with repository variable `WIKIMEDIA_MEDIA_ENABLED=true`; it is off by default and accepts only a small license allowlist with attribution/source records. Review Commons metadata and subject relevance before public use.

For a local asset, place the file under `assets/approved/`, fill its required source/license fields in `assets/approved/manifest.json`, then send `MEDIA: asset:YOUR_ASSET_ID`. For one or more HTTPS URLs, add an **exact URL** entry to `config/telegram_media_approvals.json` with `url`, `source_url`, `license`, `permission_evidence_url` and `attribution`; send the URL(s), one per line, under `MEDIA:`. A Telegram URL alone is never treated as permission. Supported direct files: JPG, PNG, WebP and MP4, up to 50 MiB. Redirects, non-public hosts, unknown licenses and corrupt files are rejected. If media fails, original typography/motion cards are used.

Never download or reuse celebrity photos, music videos, broadcasts or other creators' clips solely because they are online. Keep attribution and rights evidence; edits/zooming do not create reuse permission.

## 5. Rendering and upload flow

The bot saves the full job JSON locally under `jobs/pending/` and sends it in a GitHub `repository_dispatch` event. The running bot polls the matching Actions run and moves its local file to `jobs/private_completed/` or `jobs/failed/` when that run finishes. On the runner, the event becomes an **ephemeral** pending job; the script itself is not committed into this public repository. The runner prepares approved media, creates Edge TTS voice and word timings, builds varied 1.5–3-second scenes, burns safe-area captions into a 1080×1920 H.264/AAC video, adds original quiet music, validates with ffprobe and checks for black frames. The fallback cards are original and include the user's first-line hook and a bottom-center Lululala watermark.

Before calling YouTube, the workflow commits a hash reservation under `jobs/locks/`. It uploads privately, records the confirmed video ID under `jobs/completed/`, then changes visibility to the requested privacy. These committed files contain **IDs/hashes only**, not the script. A failed run after reservation leaves a lock to prevent an accidental duplicate; inspect the private upload and lock before manually retrying. `FORCE: true` creates an intentional new key. GitHub/YouTube failures in the brief window between private upload and receipt recording may require manual reconciliation.

The bot replies when a job is accepted. Actions sends progress plus success/failure messages to Telegram if `TELEGRAM_BOT_TOKEN` and the chat ID are configured. If an upload fails, the rendered MP4 is attached as a short-lived Actions artifact for recovery. Artifacts in a public repository should not be treated as private storage.

## 6. Test without uploading

With network access to Edge TTS:

```powershell
python -m pipeline.main --job tests/sample_job.json --no-upload
```

This writes `output/test/final.mp4`, `captions.ass`, `timeline.json`, `media_manifest.json`, `cover.png`, and `status.json` without YouTube credentials. For an offline FFmpeg-only technical smoke test, add `--offline-test-tone`; that tone cannot be uploaded through `pipeline.main`.

`pipeline.main` never uploads directly; the GitHub Actions workflow owns the duplicate reservation and private-first upload sequence.

After merge, `Actions → Telegram Requested Short → Run workflow` accepts `job_json` for a manual test. Its `no_upload` input defaults to **true**. The Telegram bot uses `repository_dispatch` and the `UPLOAD` field instead.

## Troubleshooting

- No Telegram reply: keep the bot process running, check its token and numeric allowlist IDs, and send `/short` with the complete fields in one message.
- Accepted but no Actions run: merge `render-short.yml` to the default branch, check the PAT's repository selection and Contents permission, and confirm `GITHUB_REPOSITORY`.
- No face footage: add rights-cleared media approval or enable Commons; otherwise generated cards are the intended fallback.
- TTS failure: verify network access and the selected Edge voice; the voice call retries. Burmese text requires a Burmese voice for good pronunciation.
- Duplicate refused: inspect `jobs/completed/<hash>.json` and `jobs/locks/<hash>.json`. Use `FORCE: true` only if you knowingly want another upload.
- Upload failure: inspect the Actions artifact and private video state. Keep a reservation lock until you know whether YouTube accepted the upload.
- `final.mp4` rejected: inspect `output/<job_id>/status.json` and FFmpeg logs for the exact stage/error. The validator requires video/audio streams, 1080×1920 H.264/AAC, 30 FPS and 5–180 seconds.
