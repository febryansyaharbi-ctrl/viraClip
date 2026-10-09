# ViraClip — Studio & Mentor Kreator

Private, single-owner Indonesian creator workspace. Self-hosted on a Linux VPS. No subscriptions, billing flow, fabricated earnings, or virality guarantees.

## Working features

- Password login, salted PBKDF2 hashes, HTTP-only sessions, same-origin mutation protection, login throttling.
- Durable SQLite profiles, tasks, rights records, publication calendar, metrics, and monetization progress.
- Video/audio uploads (500 MB / 120 minutes), media playback with HTTP byte ranges.
- Local Faster Whisper transcription, editable subtitles, SRT import/export.
- YouTube URL import: fetch existing manual/automatic captions and source timestamps directly (no MP3 download or ASR). Embedded preview, full/range SRT export, optional video file retrieval for authorized use, and attachment to the same original uploaded video.
- AI highlights examine the complete transcript in bounded chunks, use validated segment indices for clip boundaries, and explain value, original contribution, and context cautions.
- FFmpeg MP4 rendering: 9:16, 1:1, 16:9, manually adjustable crop position, burnt-in captions, optional original voiceover mixed over source audio.
- Personal AI coach with durable conversation history, profile/metrics context, niche comparisons with user selection, generated missions, and five-stage quest/XP progress.
- Source-backed capacity plan, editorial publication drafts, manual analytics comparisons.
- Separate early YPP and advertising thresholds, self-review checklist, and explicit-assumption revenue calculator.
- Downloadable data backup; media stays separate.

## Clear boundaries

The mentor uses a connected LLM with workspace context and a reviewed research snapshot, not live market research. XP tracks self-reported task completion, not YouTube outcomes. YouTube metrics and permissions are entered by the owner. No automated copyright clearance, face tracking, automatic YouTube uploads, background reminders, or guaranteed monetization. Crop position is manually adjustable. Caption quality requires review. Local transcription model needs an initial network download and consumes CPU/RAM. Video and AI jobs are serial. Captions/video retrieval may be refused by YouTube, in which case import SRT or upload the authorized original file; the app does not bypass restricted videos. The model sees text/timestamps, not audiovisual context. AI providers can rate-limit or become unavailable; errors are explicit and prior data remains. Restarted jobs are marked interrupted and can be retried.

Research references live in `public/research.json` and were reviewed on 2026-10-07. Verify current policy in YouTube Studio before applying. Suggested niches and publishing slots are experiments, not current RPM rankings or causal research findings.

## Run

Requires Python 3.10+, FFmpeg with libx264 and libass, and a Unicode font such as DejaVu Sans.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python server.py
```

Default bind: `127.0.0.1:8022`. Put behind a trusted HTTPS reverse proxy. For production use the included systemd unit, adjust paths/user, and expose only via HTTPS. Do not expose the Python service directly to the internet. Reverse proxy should forward Host and X-Forwarded-Proto; set proxy upload limits to at least 500 MB and appropriate timeouts.

On first start a random owner password is created in `data/initial-password.txt` (mode 0600). Alternatively set `VIRACLIP_PASSWORD` for initialization. It only applies before credentials exist. Change it in Settings; existing sessions are revoked and the initial-password file is removed. Never commit the data directory or credentials.

## Deployment

Deployed on the authorized VPS at https://harnet.tail89c9ef.ts.net:10000/ . The service is enabled for startup and is isolated from the existing services. No login secrets are stored in this repository.

The supplied service definition runs as the unprivileged owner, has a 2 GB memory ceiling, CPU limit, and private temporary directory. Existing services are left in place. HTTPS uses the VPS's existing Tailscale Funnel service on its independent port 10000. Funnel is an external availability dependency.

```sh
# From this repository, as harnet on the target VPS:
bash deploy/install-vps.sh
```

The installer clones into `/home/harnet/viraclip-studio/app`, preserves data and credentials in the parent `data/` directory, warms the speech model, runs integration tests, installs the service, and refuses to replace an unrelated HTTPS route.

Back up the data directory using SQLite's backup API while running, or stop the service for a full filesystem backup. Downloaded JSON does not include video files. Uploaded data and generated files are never committed to GitHub.

## Verification

```sh
python3 tests/integration.py
node --check public/app.js
node tests/frontend.cjs
python3 tests/intelligence_test.py
# On the VPS with the base model cached and FFmpeg flite enabled:
VIRACLIP_TEST_TRANSCRIPTION=1 .venv/bin/python tests/integration.py
```

The integration test uses isolated temporary storage and a synthetic media fixture. It covers authentication, CSRF, durable state, upload, SRT, real MP4 encoding, validation, session revocation, and deletion. It does not call YouTube or a paid AI API.

## Verification record — 2026-10-10 (Asia/Jakarta)

- Public HTTPS health endpoint and login page verified.
- Isolated integration workflow passed on the VPS: authentication, state, upload, subtitle import, actual 720×1280 MP4 render, access checks, password/session revocation, cleanup.
- Optional speech test passed: generated English speech was transcribed and contained the expected words. This verifies the pipeline, not accuracy for every language, recording, or speaker.
- Twenty empty/populated page-render checks passed, along with URL/text escaping and analytics calculation checks. Authenticated browser visual QA has not been completed.
- Pinned PyAV 15.1.0 to resolve an incompatible `metadata_errors` API in newer releases. Regular HTTPS model downloading avoids a stalled optional Xet transport on this VPS.

## AI configuration (server only)

Store `api-keys.json` in `VIRACLIP_DATA` with mode 0600, JSON keys `openrouter` and `groq`. Never put it in the public directory, source repository, logs, or browser. The server does not expose these keys through bootstrap or backup. Only authenticated requests can enqueue AI work. Limit: 60 AI jobs per rolling 24 hours; complete-transcript analysis may require multiple provider calls.

Primary model: `google/gemma-4-31b-it:free` on OpenRouter. On provider failure, fallback: `openai/gpt-oss-120b` on Groq (confirmed in the account model catalog). Conversations disclose the actual answering model/provider. API availability and account quotas apply. Caption/transcript analysis sends text to these providers; the coach sends profile, recent conversations, missions, and manually recorded metrics. No API keys are sent to models.

YouTube caption dependency: https://github.com/jdepoix/youtube-transcript-api
Provider documentation: https://openrouter.ai/docs/api-reference/overview and https://console.groq.com/docs/models

The YouTube workflow never silently falls back to speech recognition. Local Whisper remains an explicit option for uploaded media. Importing subtitles does not grant copyright permission.
