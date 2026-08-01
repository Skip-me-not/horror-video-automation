# English Horror Shorts Automation

A private-first pipeline for original 30-second English horror Shorts. n8n sends
a compact story job to GitHub Actions; GitHub generates realistic narration,
burns readable captions into a dark 9:16 video, mixes creepy ambience, uploads
the result privately to YouTube, and reports the result to n8n.

## Output

- 30 seconds, 1080x1920, H.264/AAC at 30 fps
- Chatterbox Nano English narration on a CPU runner
- Kokoro as an explicitly selected fallback (never a silent fallback)
- restrained dark voice processing, short pauses, and a natural-speed guard
- sentence-aware burned-in captions inside the Shorts safe area
- dark grading, vignette, subtle grain, fades, and optional watermark
- low-volume looped horror ambience under the narration; a generated dark room
  tone is used when no ambience asset is supplied
- YouTube title/description hashtags and Private-only upload

Chatterbox Nano is loaded with `ChatterboxTurboTTS.from_pretrained(device="cpu",
nano=True)`. It is a 110M English model intended for CPU inference and supports
paralinguistic tags. Only clone a voice when you own it or have clear permission.

Official references: [Chatterbox](https://github.com/resemble-ai/chatterbox),
[YouTube upload guide](https://developers.google.com/youtube/v3/guides/uploading_a_video).

## Required media

Add licensed files before the first run:

- `assets/backgrounds/dark-corridor.png` (an original starter visual is included)
- `assets/ambience/dark-room-tone.mp3` (optional; leave the job field empty without it)
- `assets/watermark/channel-watermark.png` (optional)

A slow-moving 1080x1920 video works best, but the renderer also supports a
portrait still with animated film grain. Landscape sources are center-cropped.
Use CC0/Public Domain ambience without speech or recognizable
copyrighted music. Large or private media can be delivered separately instead
of committed; update the workflow before relying on GitHub LFS or release URLs.

## Job format

See `examples/job.example.json`. Stories must be original English text from 180
to 480 characters. If synthesized narration cannot fit within 27.5 seconds
without exceeding a 1.12x speed adjustment, generation stops and asks for a
shorter story. The remaining time provides a brief horror beat before/after the
narration while the ambience continues.

Only `private` uploads are accepted. Review the voice, visuals, captions,
copyright status, and YouTube policy compliance in Studio before publishing.

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
After listening to that sample, dispatch **Create 30-second horror Short** from
n8n or GitHub Actions.

## GitHub secrets

Create these under **Settings -> Secrets and variables -> Actions**:

| Secret | Required | Purpose |
| --- | --- | --- |
| `YOUTUBE_CLIENT_ID` | yes | Google OAuth client ID |
| `YOUTUBE_CLIENT_SECRET` | yes | Google OAuth client secret |
| `YOUTUBE_REFRESH_TOKEN` | yes | Offline YouTube upload token |
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
