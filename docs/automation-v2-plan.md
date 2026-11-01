# BL Entertainment Shorts Automation v2

## Existing system audit

The repository currently has one production workflow, `.github/workflows/create-short.yml`.
It runs four Myanmar-time publishing slots plus one guarded retry per slot.  The workflow
installs FFmpeg and Python dependencies, downloads a Piper voice, discovers public Reddit
posts, renders a 1080x1920 H.264/AAC Short, applies deterministic source/final quality
gates, uploads through the YouTube Data API, persists rotation state with a fetch/merge/push
loop, uploads two-day diagnostic artifacts, and removes runner output.

The existing implementation is Python-first.  `reddit_source.py` performs credential-free
discovery and media URL extraction; `content_quality.py` probes, hashes, ranks, and rejects
media; `render_idol_short.py` controls discovery, narration, subtitles, FFmpeg, selection,
metadata, and state; `upload_youtube.py` performs resumable uploads and records daily IDs.
`data/reddit_state.json` is the Git-backed persistent store.  Upload secrets are limited to
`YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN`; the optional
`REDDIT_USER_AGENT` and `CHANNEL_NAME` are repository variables.  No AI API is used by the
active workflow, although legacy filenames still include `ai_script.py`.

Risks found: the active content model is K-pop/Reddit-specific; a single large renderer owns
too many concerns; Reddit popularity is not verification; media reuse permission is not
represented; story/template/layout history is not tracked separately; and the current
pipeline cannot accept a structured verified entertainment-news story.

## Implementation plan

1. Keep the existing uploader, quality utilities, schedules, and legacy renderer available.
2. Add a data-driven BL story/template engine with 100+ non-trivial definitions, deterministic
   selection, verification scoring, sensitive-claim review rules, fingerprints, and history.
3. Add 18 reusable visual layouts, six caption profiles, cover layouts, title/description/CTA/
   hashtag catalogs, and deterministic seeded selection.
4. Add a feed/queue collector that accepts configured official or reputable RSS/Atom sources,
   never upgrades an untrusted source class, and retains attribution.
5. Add a reusable FFmpeg renderer supporting authorized local/remote images or clips, a safe
   generated-card fallback, optional supplied narration, text-only mode, music, captions,
   watermark, progress bar, and cover frame.
6. Add QA, structured run logs, duplicate checks, atomic state updates, and a pipeline CLI.
7. Point the production workflow at the BL pipeline while preserving four slots, retries,
   concurrency, dry-run artifacts, YouTube upload, and safe state persistence.
8. Add fixtures and tests for every requested deterministic subsystem, then run five dry runs,
   FFprobe validation where FFmpeg is available, and the complete pytest suite.

The media-source layer is intentionally replaceable.  Remote assets are only downloaded when
their story entry explicitly marks them authorized; otherwise the renderer uses repository-
owned cards and bundled music.  Source verification and media permission are separate checks.
