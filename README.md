# Lululala K-pop Entertainment Shorts Automation

An AI-assisted, low-usage YouTube Shorts pipeline for K-pop countdown videos. It uses public
Reddit-hosted media, FFmpeg, GitHub Actions, one optional GitHub Models packaging call, and the
YouTube Data API.

## Architecture

1. `bl_source.py` finds six unused, non-NSFW public `v.redd.it` K-pop videos without a login,
   cookie export, Reddit API key, or AI service.
2. `bl_engine.py` validates the story, scores its sources, blocks sensitive claims, checks
   duplicates, chooses a template/layout deterministically, and produces script/captions/metadata.
3. `ai_optimizer.py` makes at most one compact model request per video to improve the title, first
   hook, subtitle, and comment CTA. If the model is unavailable, deterministic packaging continues.
4. `bl_ranked_renderer.py` merges each Reddit clip's original audio and renders a retention-first
   35-second 720x1280 countdown with a #1 teaser, scene-aware starts, compact labels, and watermark.
4. QA probes the output and blocks upload on technical, source, metadata, placeholder, or duplicate
   failure.
5. `upload_youtube.py` performs a resumable public upload and records the YouTube ID only after
   success.  GitHub Actions then safely merges and commits state.

Legacy modules keep their historical filenames, but the production workflow now generates only
the K-pop ranked format.

## Important directories

| Path | Purpose |
|---|---|
| `templates/manifest.json` | 100 content templates in 18 categories |
| `templates/metadata.json` | 52 titles, 20 descriptions, 10 CTAs, 10 hashtag sets |
| `config/bl_automation.json` | verification, rotation, 18 layouts, captions, music, QA |
| `data/queue/` | manually curated structured stories; `sample-*` files are never auto-selected |
| `data/bl_state.json` | template, layout, title, fingerprint, and publication history |
| `scripts/bl_*.py` | source, engine, renderer, pipeline, and state merge modules |
| `quality_reports/` | machine-readable pre-upload QA results |
| `logs/run.json` | structured run and upload status |

## Content templates

The committed catalog contains exactly 100 definitions across breaking news, casting, series
announcements, trailers, release dates, actor updates, agency updates, fan meetings, awards,
interviews, viral public moments, milestones, comebacks, collaborations, clarifications, confirmed
controversy, weekly roundups, and general entertainment.

To add template 101, add a definition to `scripts/generate_bl_catalog.py`, increment a category
count, run `python -m scripts.generate_bl_catalog`, and run the tests.  A template declares required
fields, source classes, hook/body/CTA, layout, caption/music profiles, pacing, and headline style.

Selection is seeded from `story_id`, so rebuilding the same story is reproducible.  When alternatives
exist it avoids the last 10 templates, last 8 hook patterns, and last 5 layouts.  Metadata similarly
avoids the last 10 title-pattern indexes.  Category counts are retained for reporting.

## Story JSON

See the five `data/queue/sample-*.json` fixtures.  A production story needs:

```json
{
  "story_id": "publisher-2027-series-cast",
  "category": "casting",
  "headline": "A factual, supported headline",
  "actor": "Actor One",
  "actor_2": "Actor Two",
  "series": "Series Name",
  "company": "Official Company",
  "context": "Supported context",
  "detail": "Supported detail",
  "sources": [
    {"type": "official", "name": "Official newsroom", "url": "https://publisher.example/item"}
  ],
  "assets": [
    {"path": "assets/authorized/photo.jpg", "authorized": true, "credit": "Rights holder"}
  ]
}
```

Assets are optional.  A story can specify a repository-relative `narration_file` (WAV/MP3) for
prerecorded human narration or externally supplied system TTS.  Without it, `auto` and `text-only`
modes produce caption-led video with bundled music.  The pipeline never generates a voice.

## Source verification

Base scores are official 100, reputable media 80, verified social 70, social 50, fan 30, Reddit 20,
and unknown 10.  A second reputable source adds 15, official confirmation adds 10, and matching
date/event information adds 10, capped at 100.  Scores at least 70 can be processed automatically;
40–69 require review; lower scores are rejected.

Dating, sexuality, private relationships, medical claims, crimes, and serious allegations always
require manual review regardless of score.  `allow_review` can render them only when the workflow is
also a dry run; it can never grant auto-publication.

Source verification and a public Reddit URL do not grant media rights.  The ranked format links
each original Reddit post in the YouTube description, but the channel operator must still ensure
that its use is licensed or otherwise permitted. Editing alone does not guarantee copyright or
YouTube reused-content eligibility.

## Local commands

```bash
pip install -r requirements.txt
python -m scripts.generate_bl_catalog
python -m scripts.validate_config --mode bl-short
python -m pytest -q
python -m scripts.bl_engine --input data/queue/sample-casting.json --allow-review
python -m scripts.bl_pipeline --input data/queue/sample-casting.json --dry-run --narration-mode text-only
```

FFmpeg and FFprobe must both be on `PATH`.  Output is written to `output/`, QA to
`quality_reports/`, and the structured log to `logs/run.json`.

## GitHub Actions

Open **Actions → Create K-pop entertainment Short → Run workflow**. For a safe test:

1. keep `dry_run` enabled;
2. leave narration mode on `auto` (the countdown preserves original clip audio);
3. leave `allow_review` off;
4. leave `ai_mode` on `auto` to use one compact GitHub Models call with fallback;
5. download the `kpop-short-<run id>` artifact and inspect `ai_optimization.json`.

Scheduled publishing now targets one deliberate Myanmar-time upload per day at 14:00, with a guarded
retry at 14:40. A retry reads actual successful YouTube IDs and exits when the daily target is filled.
Workflow concurrency serializes publishers so two runs cannot publish the same state. When no unused
safe clips are available, scheduled runs finish as a clean skip instead of a failure.

The optional AI call uses the built-in Actions token with the `models: read` permission. Set the
repository variables `AI_ENDPOINT` and `AI_MODEL` only when an OpenAI-compatible provider or a
different GitHub Models model is required. `ai_mode=off` disables the call, `auto` falls back to
deterministic packaging on an API failure, and `required` intentionally fails if the model is
unavailable.

The only required secrets for real uploads are `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and
`YOUTUBE_REFRESH_TOKEN`. `YOUTUBE_COOKIES_B64` is not used. `CHANNEL_NAME` remains optional and
defaults to `Lululala`. The optional `KPOP_REDDIT_SUBREDDITS` variable defaults to `kpop`;
idol-specific communities are added automatically for the selected artist.

## Rendering and QA

The renderer provides 18 reusable layouts and six caption profiles.  Captions are split on
punctuation, limited to approximately two mobile-safe lines, and timed at a configurable 165 WPM.
FFmpeg adds dark editorial cards or authorized media with blurred fill, restrained deterministic
motion, fades, headline color, watermark, progress bar, bundled music, and optional narration.  It
also extracts `cover.jpg` from the rendered design.

Before upload QA requires a decodable 1080x1920 video, configured duration, reasonable size, AAC
audio, resolved variables, non-empty metadata, an auto-publishable source, source URLs, valid assets,
known template/layout IDs, and a clean duplicate check.  A failure exits before YouTube upload and
the workflow still uploads diagnostics.

## Troubleshooting

- **Fewer than six clips:** scheduled runs cleanly skip and retry later; broaden `KPOP_REDDIT_SUBREDDITS`
  if the channel needs more variety. The workflow refuses thumbnail and black-screen substitutes.
- **AI packaging unavailable:** `auto` mode keeps the deterministic title, hook, and CTA; use
  `required` only when a model response is a hard requirement.
- **Manual review required:** inspect the source and claim; do not bypass it for production.
- **Asset rejected:** mark only genuinely authorized/configured assets with `authorized: true`.
- **FFprobe missing:** the workflow checks for both FFmpeg and FFprobe, retries apt installation, and
  fails clearly if the GitHub runner cannot resolve package servers.
- **Upload credentials missing:** use dry-run or add the three existing YouTube secrets.
- **Duplicate blocked:** source collection now filters published IDs, URLs, fingerprints, and headlines;
  do not delete history to repost the same item.
- **Feed has no usable entries:** verify it is RSS/Atom and its URL is reachable from GitHub Actions.

GitHub scheduling and YouTube availability are external systems: no repository can guarantee a run
starts or an API upload succeeds during an outage or quota limit.  The guarded retries cover normal
transient delay without counting a render as a publication.
