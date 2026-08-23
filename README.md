# Automated Strange Incident Shorts

An unattended English YouTube Shorts pipeline that explains **one documented strange incident per video**. Each Short opens with a direct hook, reconstructs the event in chronological order, distinguishes confirmed evidence from disputed claims, and links its source.

## Evidence policy

Every Short clearly separates two claims:

- The archive verifies that an account, performance, belief, interview, or folklore record exists.
- The archive does **not** prove that a supernatural explanation is true.

Entries use `oral_history`, `folklore_record`, `archival_record`, or `reference_summary`. Titles never use unsupported “TRUE STORY” claims. The description includes the direct URL, rights note, evidence label, and verification caveat.

## Production incident bank

`data/incident_bank.json` is the production idea bank. Every `EV` entry contains a hook, a 45–110 word explanation, date, location, source, red-emphasis terms, and at least four event-specific dark visual searches. The older 500-item `data/script_bank.json` remains as a research archive and is not selected while the incident bank exists.

Validate both banks with:

```bash
python scripts/build_script_bank.py --target 500 --refresh-sources
python scripts/validate_bank.py
```

The builder uses Library of Congress archive metadata plus attributed English Wikipedia reference summaries from horror/folklore categories. It caches metadata in `data/fact_sources.json` and writes scripts to `data/script_bank.json`. IDs run from `HF0001` to `HF0500`. Each script is 60–100 words and has a unique direct source URL. Wikipedia-derived entries are labeled `reference_summary`, not primary evidence.

The incident scripts do not claim that legends or paranormal explanations are proven. They state what was recorded, what investigators concluded, and what remains uncertain.

## Run

```bash
python scripts/generate_short.py --dry-run
python scripts/generate_short.py --no-upload
python scripts/generate_short.py
python scripts/generate_short.py --dry-run --script-id EV0001
```

`--dry-run` changes no state. `--no-upload` renders without publishing or marking an incident used. Failures leave the incident `ready`.

## Visuals and audio

Each incident becomes 4–10 event-specific dark documentary scenes. Captions use bold white text, red emphasis for names/dates/evidence, and a subtly blurred dark band behind the text. The media layer can use licensed local assets, Pexels, Pixabay, Wikimedia Commons, and Internet Archive; arbitrary YouTube, film, and television footage is never downloaded.

Original creepy ambience, music, and sparse SFX are generated while narration remains dominant. Optional stock keys:

```text
PEXELS_API_KEY
PIXABAY_API_KEY
```

## YouTube and GitHub Actions

Publishing needs `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN` with YouTube upload scope. Never commit credentials.

- `build-bank.yml` manually refreshes and validates the sourced fact bank.
- `generate-short.yml` runs manually or at 08:00 and 20:00 Myanmar time (`01:30` and `13:30` UTC).
- Successful uploads update the bank and state files.
- A shared concurrency group prevents simultaneous state writes.

Scheduled GitHub jobs are best-effort and can start several minutes late.

## Requirements and tests

Python 3.11+, FFmpeg/ffprobe, dependencies from `requirements.txt`, and outbound access for source refresh, edge-tts, stock APIs, and upload.

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```
