# English Horror Shorts Automation

A public-upload pipeline for original, variable-length English horror Shorts. n8n sends
a compact story job to GitHub Actions; GitHub generates realistic narration,
burns readable captions into a dark 9:16 video, mixes creepy ambience, uploads
manual and scheduled results publicly to YouTube and reports the result to n8n.

## Output

- 20-179 seconds, 1080x1920, H.264/AAC at 30 fps; narration determines length
- Kokoro `am_michael` natural American male narration with restrained horror tone
- Chatterbox Nano remains available as an explicitly selected alternative
- subtle dark voice processing, continuous storytelling, and a natural-speed guard
- sentence-aware burned-in captions inside the Shorts safe area
- dark grading, vignette, subtle grain, fades, and a top-center text watermark
- audible original horror drone, cold wind, distant swells, knocks, heartbeat,
  ending sting, and subtle reversed whispers
- original cinematic horror music with minor chords, eerie melody, and bass pulses
- layered dark room tone remains underneath the generated soundscape
- 3-10 changing scenes from Pexels, Pixabay, Wikimedia Commons, and Internet Archive
- deterministic provider/page rotation so concurrent jobs do not all choose the same clip
- YouTube title/description hashtags and Public-only upload

Kokoro's `am_michael` voice is the default so every automated run uses a clearly
male English narrator. Chatterbox Nano remains selectable and is loaded with
`ChatterboxTurboTTS.from_pretrained(device="cpu", nano=True)`. Only clone a voice
when you own it or have clear permission.

Official references: [Chatterbox](https://github.com/resemble-ai/chatterbox),
[YouTube upload guide](https://developers.google.com/youtube/v3/guides/uploading_a_video).

## Required media

The included corridor remains the safe fallback. Optional local assets:

- `assets/backgrounds/dark-corridor.png` (an original starter visual is included)
- `assets/ambience/dark-room-tone.mp3` (optional; leave the job field empty without it)
The validated `watermark_text` job field is always drawn in the upper-center
safe area. The default is `SKIP IF YOU'RE SCARED`; no PNG watermark is used.

For the largest pool, create free Pexels and Pixabay API keys and add them as
`PEXELS_API_KEY` and `PIXABAY_API_KEY` GitHub secrets. Wikimedia Commons and
Internet Archive are keyless fallbacks. Every provider is queried through its
documented API, downloads are capped at 60 MB per scene, licenses are filtered,
and source/creator credits are appended to the YouTube description. A failed
provider does not stop the job: the next provider is tried, then the included
corridor is used for any scene that still cannot be filled.

A slow-moving 1080x1920 video works best, but the renderer also supports a
portrait still with animated film grain. Landscape sources are center-cropped.
Use CC0/Public Domain ambience without speech or recognizable
copyrighted music. Large or private media can be delivered separately instead
of committed; update the workflow before relying on GitHub LFS or release URLs.

## Job format

See `examples/job.example.json`. Stories may contain 220-2200 characters. The
voice is kept at its natural speed. The final duration is narration plus a
job-seeded 1.5-4.5 second ending beat, clamped to 20-179 seconds so the vertical
result remains within YouTube's three-minute Shorts limit. Scene count grows
from 3 to 10 with the duration.

Manual and scheduled runs always publish as `public`; the workflow no longer
offers a privacy selector. Review the voice, visuals, captions, copyright status,
and YouTube policy compliance before running it on a channel.

## Genre-balanced story bank

`ideas/horror-stories.json` contains 500 numbered scripts across 20 distinct
horror genres: paranormal, psychological, cosmic, folk, gothic, body, creature,
technology, analog, liminal, urban legend, occult, survival, maritime, and time
horror. Scripts also rotate among confession, incident-report, and traditional
narration structures. In **Actions -> Create dynamic horror Short**, leave
`job_payload` empty, enter a unique `job_id`, and set `idea_number` from 1 to
500. Existing n8n payload dispatches remain supported.

The repository intentionally does not commit a counter after every run. Track
the next number in n8n (or enter it manually); this avoids concurrent runs
overwriting each other and avoids unnecessary GitHub commits. After idea 500,
replace the JSON entries with another valid bank and restart at 1. Regenerate
the included starter bank with:

```bash
python scripts/generate_idea_bank.py
```

The text catalog is small and does not meaningfully load GitHub. Video,
audio, TTS model, and render outputs remain outside Git history.

## Local checks

Prerequisites: Python 3.11, FFmpeg/ffprobe, and `espeak-ng` for Kokoro.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python scripts/validate_job.py --job examples/job.example.json
```

Use **Actions -> Test voice** first. It downloads the selected local TTS model,
generates a short sample and captions, and uploads them as a one-day artifact.
The workflow explicitly installs PyTorch's CPU wheels so GitHub does not waste
runner disk or setup time on unused CUDA packages.
After listening to that sample, dispatch **Create dynamic horror Short** from
n8n or GitHub Actions.

## GitHub secrets

Create these under **Settings -> Secrets and variables -> Actions**:

| Secret | Required | Purpose |
| --- | --- | --- |
| `YOUTUBE_CLIENT_ID` | yes | Google OAuth client ID |
| `YOUTUBE_CLIENT_SECRET` | yes | Google OAuth client secret |
| `YOUTUBE_REFRESH_TOKEN` | yes | Offline YouTube upload token |
| `PEXELS_API_KEY` | no | Free dynamic portrait background videos |
| `PIXABAY_API_KEY` | no | Additional free background-video pool |
| `N8N_CALLBACK_URL` | no | Overrides the validated callback URL |

The refresh token must be authorized by the Google account that owns the target
YouTube channel. An OAuth consent screen left in Testing can issue refresh tokens
that expire after seven days.

## Separate GitHub account

This directory is intended to become its own private repository, independent of
the motivational Shorts project:

```bash
git init
git add .
git commit -m "Add English horror Shorts automation"
git branch -M main
gh auth login
gh repo create OWNER/horror-shorts-automation --private --source . --remote origin --push
```

Run `gh auth status` first and make sure the active account is the new account.
Do not reuse the old repository remote or commit OAuth/client secret files.

## n8n

Import `n8n/horror-video-orchestrator.json` and follow `n8n/SETUP.md`. Configure
the new GitHub owner, repository name, branch, callback URL, and a fine-grained
token restricted to that repository. The exported workflow contains no secret.

## Safety and operations

- The repository should be private.
- Uploads remain Private until a human publishes them.
- Do not clone celebrities, creators, or other people without permission.
- Avoid graphic gore, flashing imagery, misleading real-event claims, and
  repetitive low-value uploads.
- GitHub-hosted runners have no exact timing SLA; begin with manual runs.
- Model caches are retained, but generated narration/video is not cached.
