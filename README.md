# ViraClip — Studio & Mentor Kreator

Private, single-owner Indonesian creator workspace. Self-hosted on a Linux VPS. No subscriptions, billing flow, fabricated earnings, or virality guarantees.

## Working features

- Password login, salted PBKDF2 hashes, HTTP-only sessions, same-origin mutation protection, login throttling.
- Durable SQLite profiles, tasks, rights records, publication calendar, metrics, and monetization progress.
- Video/audio uploads (500 MB / 120 minutes), media playback with HTTP byte ranges.
- Local Faster Whisper transcription, editable subtitles, SRT import/export.
- Transcript-based candidate clip selection (explicitly a heuristic, not a viral prediction).
- FFmpeg MP4 rendering: 9:16, 1:1, 16:9, manually adjustable crop position, burnt-in captions, optional original voiceover mixed over source audio.
- Source-backed structured mentor, niche hypotheses, 14-day workflow, publication drafts, manual analytics comparisons.
- Separate early YPP and advertising thresholds, self-review checklist, and explicit-assumption revenue calculator.
- Downloadable data backup; media stays separate.

## Clear boundaries

The mentor uses transparent editorial rules and a reviewed research snapshot, not a connected conversational LLM or live market data. YouTube metrics and permissions are entered by the owner. No automated copyright clearance, face tracking, automatic YouTube uploads, background reminders, or guaranteed monetization. Crop position is manually adjustable. Caption quality requires review. Local transcription model needs an initial network download and consumes CPU/RAM. Rendering jobs are serial. Restarted jobs are marked interrupted and can be retried.

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

Deployment is prepared but not yet verified on the VPS. The last deployment connection was blocked because the authorized Desktop Commander device was offline.

The supplied service definition runs as the unprivileged owner, has a 2 GB memory ceiling, CPU limit, and private temporary directory. Existing services are left in place. The intended HTTPS route uses the VPS's existing Tailscale Funnel service on its independent port 10000. Funnel is an external availability dependency.

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
```

The integration test uses isolated temporary storage and a synthetic media fixture. It covers authentication, CSRF, durable state, upload, SRT, real MP4 encoding, validation, session revocation, and deletion. It does not call YouTube or a paid AI API.
