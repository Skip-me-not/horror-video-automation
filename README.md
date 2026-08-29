# Authorized Horror Podcast to Edited Short

This repository creates 65–175 second vertical horror-story videos from source media that you own or
are authorized to download and reuse. It uses deterministic transcript, audio-energy, and silence rules;
there is no AI or LLM moment detector.

The output is an edited story rather than a continuous podcast crop: a 2–5 second hook, mirrored and
speed-adjusted speaker footage, animated captions, deterministic crop changes, and transcript-relevant
Pexels/Pixabay inserts. The original source narration remains continuous beneath every reference visual.

## Safety and source authorization

Automated search only accepts video IDs or channel IDs listed in the repository settings or supplied by
the `AUTHORIZED_VIDEO_IDS` and `AUTHORIZED_CHANNEL_IDS` secrets. A manual remote URL also requires the
`--authorized` flag. Use that flag only when you own the source or have permission to download, edit, and
republish it. Supplying a local file is treated as an explicit user-provided authorized source.

Mirroring, cropping, captions, and speed changes do not create copyright permission. Keep written proof
of the license or creator authorization outside this repository.

## Pipeline

1. Search source metadata before downloading and reject Shorts, livestreams, duplicates, sources under
   10 minutes, sources over 180 minutes, and sources outside the authorization allowlist.
2. Download one accepted source and available English VTT captions.
3. Score caption moments using configured hook, paranormal, fear, mystery, sound, visual, confession,
   twist, proximity, silence-boundary, and payoff rules.
4. Expand the strongest anchor into a coherent 70–165 second source segment.
5. Mirror, play at 1.10x, preserve pitch, and reframe without stretching to 1080x1920.
6. Generate a deterministic 2–5 second hook and animated ASS captions with highlighted horror terms.
7. Build short reference queries only from visual transcript events. Pexels falls back to Pixabay, then
   to uninterrupted speaker footage if no licensed stock asset is available.
8. Write and validate `edit_plan.json` before rendering. B-roll normally covers 15–35 percent, lasts
   2–6 seconds per insert, and never replaces the continuous narration track.
9. Render H.264/AAC at 30 FPS and fail if ffprobe does not confirm the format, duration, audio/video
   alignment, and minimum file size.

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

Allowlisted metadata search:

```bash
python -m src.main --keyword "true scary stories podcast"
```

Other supported controls:

```text
--source-speed 1.10
--target-duration 110
--no-stock
--force-reprocess
--debug
```

## Configuration and secrets

The five JSON files in `config/` control search terms, horror triggers, reference query mappings,
scoring, duration, transforms, crop mode, and provider behavior.

Configure these GitHub repository secrets:

```text
AUTHORIZED_VIDEO_IDS       comma-separated exact video IDs
AUTHORIZED_CHANNEL_IDS     comma-separated exact channel IDs
PEXELS_API_KEY              optional
PIXABAY_API_KEY             optional
```

At least one authorization allowlist secret is required for scheduled source search. Stock keys are
optional; generation falls back to source footage when both are unavailable.

## GitHub Actions

Only `.github/workflows/horror-short-generator.yml` is active. Manual runs accept `video_url`,
`keyword`, `source_speed`, `target_duration`, `use_stock_media`, `force_reprocess`, and an explicit
authorization confirmation.

Scheduled runs preserve the previously selected four daily US audience windows:

- 16:07 UTC — US East midday / US West morning
- 19:07 UTC — US East afternoon / US West midday
- 22:07 UTC — US East evening / US West afternoon
- 01:07 UTC — US East late evening / US West early evening

GitHub evaluates scheduled workflow cron entries in UTC, so local US clock times move by one hour at
daylight-saving transitions. Successful runs commit only the lightweight duplicate history. Downloads
and temporary media are deleted after artifacts are uploaded.

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
```

Artifacts are retained for five days. The downloaded full source is never included.
