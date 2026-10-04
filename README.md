# Lululala Celebrity Shorts

This repository automatically turns Reddit-hosted celebrity videos into vertical YouTube Shorts for the **Lululala** channel. It prioritizes K-pop idols and groups while still covering widely discussed international celebrities.

## What each run does

1. Reads current top-week posts from configured K-pop and pop-culture subreddits.
2. Accepts only posts with a direct `v.redd.it` video and skips source IDs already used.
3. Chooses K-pop content about 75% of the time and global celebrity content about 25% of the time.
4. Downloads the original Reddit-hosted clip and rejects broken, very short, or nearly black video.
5. Builds a short, source-specific English recap from the post title, meaningful body text, and up to two attributed Reddit comments. Generic RSS boilerplate and posts without enough concrete detail are skipped; rumors are never presented as verified facts.
6. Opens with a source-derived hook, then shows the clip in order before one replay rather than random repeated offsets or horizontal flips. Narration, white captions, hot-pink emphasis, and a centered `Lululala` watermark remain.
7. Ends when the narration ends (roughly 10–60 seconds), validates the vertical MP4, uploads it publicly to YouTube, records the source ID, and removes generated media.

The source pool is cached in `data/celebrity_source_pool.json`, so temporary Reddit rate limits do not automatically stop a run. The workflow retries a failed build twice before failing. Four scheduled starts are not a promise of four uploads: if none of the candidates provides enough reliable detail, the run fails instead of publishing a padded generic Short.

## Schedule

`.github/workflows/horror-short-generator.yml` is the only active production workflow. It runs four times daily at:

- 06:00 Myanmar time
- 08:00 Myanmar time
- 20:00 Myanmar time
- 21:00 Myanmar time

GitHub Actions schedules use UTC and may start several minutes late. Manual runs are also available from **Actions → Lululala Celebrity Shorts → Run workflow**.

## Required GitHub secrets

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

The refresh token determines the destination YouTube channel. It must belong to the Lululala channel before enabling public uploads.

## Source and rights note

Every description links to the original Reddit post. Editing, reframing, narration, and attribution do not automatically make third-party video copyright-free; the channel owner remains responsible for permission, platform rules, and takedown requests.

## Local checks

```powershell
python -m pytest -q
python -m src.reddit_pipeline
```

The second command needs FFmpeg, network access, and the Python packages in `requirements.txt`. Uploading is a separate workflow step and requires the YouTube secrets.
