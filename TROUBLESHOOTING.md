# Troubleshooting

## No video was produced

Open `output/result.json` or the Actions log. `no_verified_topic` is a safe result: reachable feeds did not provide a fresh, supported topic. The system does not invent filler. `research_review` means a time-sensitive or contradictory claim needs a human.

## GitHub schedule appears late

GitHub schedules are best-effort and can be delayed during load. The workflow derives the idempotent slot from the scheduled expression, not its actual start time. Run **Optional Catch-up** or **Failed Job Recovery** with the original slot ID.

## `invalid_grant` / OAuth failure

The refresh token may be revoked, belong to another OAuth client, or lack required scopes. Re-run `tools/get_refresh_token.py` and replace all three YouTube secrets together. Do not paste them into logs or issues.

## `quotaExceeded`

Do not retry repeatedly. Leave the item pending and wait for quota reset or request quota through Google. Four uploads are configurable but never guaranteed by this repository.

## FFmpeg quality rejection

Inspect `output/quality-report.json`. Upload steps are gated on successful source, license, duration, resolution, codec, audio sync, black-frame, and file-size checks.

## Analytics fields are unavailable

Unavailable means the OAuth token/API does not expose the metric; it is not recorded as zero. Reauthorize with YouTube read and Analytics read-only scopes if those metrics are required.

## Approved asset rejected

Confirm the file exists under `assets/approved/` and its manifest entry includes `id`, relative `path`, `license`, `source_url`, `attribution`, and `approved_at`. Arbitrary public URLs are not accepted as proof of reuse rights.
