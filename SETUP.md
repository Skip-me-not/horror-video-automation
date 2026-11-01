# Production setup

## GitHub configuration

| Name | Kind | Required |
|---|---|---|
| `YOUTUBE_CLIENT_ID` | Secret | For non-dry-run uploads |
| `YOUTUBE_CLIENT_SECRET` | Secret | For non-dry-run uploads |
| `YOUTUBE_REFRESH_TOKEN` | Secret | For non-dry-run uploads |
| `CHANNEL_NAME` | Variable | No; defaults to `Lululala` |
| `BL_SOURCE_FEEDS_JSON` | Variable | For scheduled feed collection when no queue story exists |

No AI, LLM, image-generation, voice-generation, Reddit, or OpenCode credential is used.

## First safe run

Open **Actions → Create BL entertainment Short → Run workflow** and set:

- `dry_run`: enabled
- `story_file`: `data/queue/sample-casting.json`
- `narration_mode`: `text-only`
- `allow_review`: disabled

The artifact contains the MP4, cover, structured story/package/metadata, QA report, and run log.
Dry-run never calls the YouTube uploader.

## Production stories

Add a non-`sample-*` JSON file under `data/queue/`, or configure an official/reputable RSS/Atom
source through `BL_SOURCE_FEEDS_JSON` as documented in the README.  Queue entries take priority.
Every source URL is attributed; every media asset also needs an independent `authorized: true`
declaration.  Source trust is not treated as a media license.

Scheduled runs use four primary Myanmar-time slots and four guarded retries.  Only successful
YouTube IDs count toward the daily target.  State is committed after upload, never after render.

See `README.md` for schema, verification rules, local commands, template extension, rendering,
copyright considerations, and troubleshooting.
