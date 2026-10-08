#!/usr/bin/env bash
# Run as harnet from an authorized SSH session. Never place passwords in this file.
set -euo pipefail
base_dir=/home/harnet/viraclip-studio
app_dir="$base_dir/app"
repo_url=https://github.com/febryansyaharbi-ctrl/viraClip.git
if [ "$(id -un)" != harnet ]; then
  echo 'Run as harnet (sudo is requested only for installing the service and HTTPS route).' >&2
  exit 1
fi
for executable in python3 git ffmpeg ffprobe tailscale; do
  command -v "$executable" >/dev/null || { echo "Missing dependency: $executable" >&2; exit 1; }
done
mkdir -p "$base_dir/data" /home/harnet/.cache
chmod 700 "$base_dir/data"
if [ -d "$app_dir/.git" ]; then
  [ "$(git -C "$app_dir" remote get-url origin)" = "$repo_url" ] || { echo 'Unexpected repository; no files changed.' >&2; exit 1; }
  [ -z "$(git -C "$app_dir" status --porcelain)" ] || { echo 'Local changes found; reconcile before deploying.' >&2; exit 1; }
  git -C "$app_dir" pull --ff-only origin main
elif [ -e "$app_dir" ]; then
  echo 'App directory already exists without expected Git metadata; no files changed.' >&2
  exit 1
else
  git clone --branch main "$repo_url" "$app_dir"
fi
if [ ! -x "$base_dir/.venv/bin/python" ]; then python3 -m venv "$base_dir/.venv"; fi
"$base_dir/.venv/bin/pip" install -r "$app_dir/requirements.txt"
"$base_dir/.venv/bin/python" -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8', cpu_threads=2); print('Transcription model ready.')"
"$base_dir/.venv/bin/python" "$app_dir/tests/integration.py"
# Refuse to change an occupied HTTPS port unless it is already our route.
route_json=$(tailscale funnel status --json)
if printf '%s' "$route_json" | python3 -c 'import sys,json; x=json.load(sys.stdin); sys.exit(0 if "10000" in x.get("TCP",{}) else 1)'; then
  printf '%s' "$route_json" | python3 -c 'import sys,json; x=json.load(sys.stdin); assert any(k.endswith(":10000") and v.get("Handlers",{}).get("/",{}).get("Proxy")=="http://127.0.0.1:8022" for k,v in x.get("Web",{}).items()), "HTTPS port 10000 belongs to another app; refusing to replace it"'
fi
sudo install -m 644 "$app_dir/deploy/viraclip-studio.service" /etc/systemd/system/viraclip-studio.service
sudo systemctl daemon-reload
sudo systemctl enable viraclip-studio.service
sudo systemctl restart viraclip-studio.service
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:8022/api/health >/dev/null; then break; fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:8022/api/health
sudo tailscale funnel --bg --https=10000 http://127.0.0.1:8022
sudo systemctl is-active viraclip-studio.service
tailscale funnel status
printf '\nPassword location (read privately): %s/data/initial-password.txt\n' "$base_dir"
printf 'Change the initial password in Settings after login. Existing passwords are preserved.\n'
