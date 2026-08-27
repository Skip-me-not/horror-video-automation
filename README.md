# Automated Interactive Horror Shorts

This repository generates retention-focused interactive horror mini-games, renders them as validated
1080x1920 YouTube Shorts, and can upload them through the official YouTube Data API. The scheduled
pipeline runs entirely on GitHub Actions; no always-on local computer or paid media API is required.

## What it generates

Six game formats are included: `choose_door`, `find_ghost`, `spot_change`, `escape_room`,
`safe_object`, and `moving_entity`. Every run first creates validated `game.json`, then builds a
15–16 second timeline with an immediate hook, interaction, countdown, reveal, outcome, and replay cue.
Three original, project-bound cinematic plates cover the hospital, haunted-room, and CCTV formats;
Pillow and FFmpeg add safe-area UI, controlled camera drift, scanlines, shadows, and reveal markers.
The local sound engine builds stereo drones, accelerating heartbeat, countdown ticks, risers, and
payoff impacts without depending on a copyrighted music library.

## Retention design

- The visual threat and cold-open appear in the first 0.65 seconds.
- The viewer receives a concrete choice or search task within three seconds.
- A four- or five-second countdown creates active participation and rising time pressure.
- The answer is shown visibly on the scene instead of being explained only by text.
- The final 1.5 seconds reconnect to the opening and invite a replay without a long outro.
- Game-specific titles and comment prompts ask for a simple answer such as A/B or 01/02/03.

These choices improve the inputs YouTube exposes for evaluation—chose-to-view, watch duration,
percentage viewed, rewatches, and engagement—but no implementation can guarantee a particular view count.

The default YouTube privacy is **private**. Set the repository variable `YOUTUBE_PRIVACY_STATUS` to
`unlisted` or `public` only after a private upload has been reviewed successfully.

## Test locally

Install Python 3.11+, FFmpeg/ffprobe, and dependencies:

```bash
python -m pip install -r requirements.txt
python -m src.main --no-upload
python -m src.main --game choose_door --seed 1234 --no-upload
```

Outputs are written to `output/`, including `short.mp4`, `game.json`, `metadata.json`, validation,
render logs, and the upload log. A video is never uploaded unless rendering and ffprobe validation pass.

## YouTube OAuth setup

1. Create a Google Cloud project.
2. Enable **YouTube Data API v3**.
3. Configure an OAuth consent screen and add your YouTube account as a test user if the app is in testing.
4. Create an OAuth client of type **Desktop app** and download its JSON file.
5. Run `python tools/get_refresh_token.py path/to/client_secret.json` once and approve the account.
6. In GitHub, open **Settings → Secrets and variables → Actions** and create these repository secrets:
   `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN`.

Never commit the client JSON, access token, refresh token, or secret. The uploader refreshes its access
token on every run and fails clearly without regenerating the video when authentication is invalid.

## GitHub Actions

Use **Actions → Interactive Horror Shorts → Run workflow**. Keep `upload` disabled to render and validate
without publishing. Enable it only for a deliberate manual private-upload test.

After setup, `.github/workflows/horror-shorts.yml` runs at these Myanmar times:

- 07:00 (`00:30 UTC`)
- 12:00 (`05:30 UTC`)
- 15:00 (`08:30 UTC`)
- 19:00 (`12:30 UTC`)

Scheduled runs upload automatically, initially as private videos. Concurrency prevents overlapping
uploads. Successful uploads are appended to the last-100 `data/history.json` records and committed back
to the repository. SHA-256 duplicate detection blocks upload of an identical rendered file.

The older documented-incident workflow remains available for manual use but has no schedule.

## Reliability rules

- Game generation retries up to twice, then uses a deterministic local fallback.
- Rendering retries once.
- Authentication failure stops before upload and never triggers regeneration.
- Transient YouTube 5xx failures use resumable upload retries with exponential backoff.
- Validation requires 1080x1920, 30 FPS, H.264, AAC, 15–30 seconds, and a non-trivial file size.
- Actions artifacts retain the video, game, metadata, validation, and logs for three days.
