# Automated Sourced Horror Fact Shorts

An unattended English YouTube Shorts pipeline for **documented horror facts, recorded experiences, and oral traditions**. It no longer generates fictional first-person stories. Each bank entry is derived from a Library of Congress catalog record and includes a direct source link.

## Evidence policy

Every Short clearly separates two claims:

- The archive verifies that an account, performance, belief, interview, or folklore record exists.
- The archive does **not** prove that a supernatural explanation is true.

Entries use `oral_history`, `folklore_record`, `archival_record`, or `reference_summary`. Titles never use unsupported “TRUE STORY” claims. The description includes the direct URL, rights note, evidence label, and verification caveat.

## Fact bank

```bash
python scripts/build_script_bank.py --target 500 --refresh-sources
python scripts/validate_bank.py
```

The builder uses Library of Congress archive metadata plus attributed English Wikipedia reference summaries from horror/folklore categories. It caches metadata in `data/fact_sources.json` and writes scripts to `data/script_bank.json`. IDs run from `HF0001` to `HF0500`. Each script is 60–100 words and has a unique direct source URL. Wikipedia-derived entries are labeled `reference_summary`, not primary evidence.

The synthetic `ideas/horror-stories.json` bank and fictional premise generators were removed. `data/script_bank.json` is the single authoritative idea/fact bank.

## Run

```bash
python scripts/generate_short.py --dry-run
python scripts/generate_short.py --no-upload
python scripts/generate_short.py
python scripts/generate_short.py --dry-run --script-id HF0042
```

`--dry-run` changes no state. `--no-upload` renders without publishing or marking a fact used. Failures leave the fact `ready`.

## Visuals and audio

Each fact becomes 4–8 historically grounded, symbolic scene prompts that do not present generated imagery as evidence. The media layer can use licensed local assets, Pexels, and Pixabay; arbitrary YouTube, film, and television footage is never downloaded.

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
