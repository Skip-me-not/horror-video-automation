# Random Horror Podcast to Edited Short

This repository creates 65–175 second vertical horror-story videos from source media. Scheduled runs
choose a random configured keyword, search metadata, and randomly select an eligible result. It uses
deterministic transcript, audio-energy, and silence rules; there is no AI or LLM moment detector.

The output is an edited scary podcast segment rather than a blind continuous crop: the pipeline finds a
high-confidence horror anchor, expands it to a complete setup/payoff window, adds a 2–5 second hook,
mirrors and speeds the speaker footage, burns animated captions, and inserts transcript-relevant
Pexels/Pixabay media. Original podcast narration remains continuous beneath every reference visual.

## Safety and source authorization

Automated keyword search does not require video-ID/channel-ID lists and does not enforce a reuse-license
metadata filter. It only filters duration, livestreams, duplicates, and unavailable metadata. You remain
responsible for confirming permission before publishing the generated edit. A manual remote URL still
requires the `--authorized` flag. Supplying a local file is treated as user-provided source media.

Mirroring, cropping, captions, and speed changes do not create copyright permission. Keep written proof
of the license or creator authorization outside this repository.

## Pipeline

1. Pick a random horror keyword, inspect up to 20 search results before downloading, and reject Shorts,
   livestreams, duplicates, sources under 10 minutes, and sources over 180 minutes.
2. Retrieve English VTT captions without downloading video and reject weak transcripts early.
3. Score caption moments using configured hook, paranormal, fear, mystery, sound, visual, confession,
   twist, proximity, silence-boundary, and payoff rules.
4. Download compressed audio only and scan silence/energy around the top transcript candidates.
5. Expand the strongest anchor into a coherent 70–165 second source segment, then download only that
   video timestamp range with three-second edit handles. Full-video download is an explicit fallback.
6. Generate a deterministic 2–5 second hook and one ASS caption file with highlighted horror terms.
7. Build exact B-roll slots before downloading anything. Pexels falls back to Pixabay, then
   to uninterrupted speaker footage if no licensed stock asset is available.
8. Download at most seven unique B-roll assets, normally five, at 2.5–4.5 seconds each.
9. Apply trim, 1.10x pitch-preserving playback, horizontal mirror, 9:16 crop, hook treatment, B-roll,
   captions, and continuous audio in one FFmpeg filter graph and one final full-resolution encode.
10. Validate H.264/AAC, 1080x1920, 30 FPS, duration, and audio/video alignment with one cached probe.

## Local commands

Install Python 3.11+, FFmpeg/ffprobe, and the dependencies:

```bash
python -m pip install -r requirements.txt
```

Authorized remote source:

```bash
python -m src.main --video-url "https://youtube.com/watch?v=AUTHORIZED_ID" --authorized
```

Authorized local source with an optional same-name `.vtt` sidecar:

```bash
python -m src.main --video-url "/path/to/authorized-source.mp4" --start 760 --no-stock
```

Random metadata search using a specified keyword:

```bash
python -m src.main --keyword "true scary stories podcast"
```

Other supported controls:

```text
--source-speed 1.10
--target-duration 110
--no-stock
--force-reprocess
--debug-artifacts
--debug
```

## Configuration and secrets

The five JSON files in `config/` control search terms, horror triggers, reference query mappings,
scoring, duration, transforms, crop mode, and provider behavior.

Required GitHub repository secrets for public upload:

```text
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN
```

Source download and stock secrets:

```text
YOUTUBE_COOKIES_B64          recommended for GitHub-hosted runners
PEXELS_API_KEY              optional
PIXABAY_API_KEY             optional
```

`YOUTUBE_COOKIES_B64` is a base64-encoded Netscape cookies file. The pipeline requires the original
podcast video and will fail safely instead of substituting an audio-only RSS episode when YouTube blocks
logged-out GitHub runner traffic. Original footage is center-cropped, fixed-zoomed to 108%, and
horizontally flipped. Stock keys are optional; B-roll falls back to the transformed original footage.

## GitHub Actions

Only `.github/workflows/horror-short-generator.yml` is active. Manual runs accept `video_url`,
`keyword`, `source_speed`, `target_duration`, `use_stock_media`, `force_reprocess`, and an explicit
authorization confirmation, and an optional `debug_artifacts` switch.

Scheduled runs preserve the previously selected four daily US audience windows:

- 16:07 UTC — US East midday / US West morning
- 19:07 UTC — US East afternoon / US West midday
- 22:07 UTC — US East evening / US West afternoon
- 01:07 UTC — US East late evening / US West early evening

GitHub evaluates scheduled workflow cron entries in UTC, so local US clock times move by one hour at
daylight-saving transitions. The job uses `ubuntu-24.04`, a 45-minute timeout, and one
`$RUNNER_TEMP/horror-short` directory. Successful runs commit only the lightweight duplicate history.
Temporary source/audio/stock media, workflow-specific caches, and the local final MP4 are deleted after
the confirmed public upload.

## Outputs

```text
output/short.mp4
output/source_info.json
output/selected_story.json
output/hook.json
output/edit_plan.json
output/reference_media.json
output/captions.ass
output/validation.json
output/processing.log
output/performance.json
output/optimization_report.md
```

Normal successful runs keep no video artifact because the confirmed public YouTube upload is the output.
Manual `debug_artifacts` runs may retain small diagnostics for five days. Downloaded source ranges,
analysis audio, stock originals, and render temp files are never retained.
