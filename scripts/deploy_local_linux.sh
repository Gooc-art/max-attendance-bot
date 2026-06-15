#!/bin/bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_DIR="${SKUD_DEPLOY_DIR:-$HOME/skud}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

mkdir -p "$DEPLOY_DIR"

rsync -a --delete \
  --exclude '.git/' \
  --exclude '.github/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.env' \
  --exclude 'data/' \
  --exclude 'logs/' \
  --exclude 'run/' \
  --exclude 'secure/' \
  "$SOURCE_DIR/" \
  "$DEPLOY_DIR/"

mkdir -p "$DEPLOY_DIR/data" "$DEPLOY_DIR/logs" "$DEPLOY_DIR/run"

cd "$DEPLOY_DIR"
ORIGINAL_HOME="$HOME"
if [ -f .env ]; then
  set -a
  . .env
  set +a
fi
export HOME="$ORIGINAL_HOME"
export SKUD_DEPLOY_DIR="$DEPLOY_DIR"
mkdir -p "$HOME/.cache/pip" || true
"$PYTHON_BIN" -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

chmod +x scripts/*.sh
bash scripts/install_systemd_user_linux.sh

systemctl --user restart skud-backend.service
if ! systemctl --user is-active --quiet skud-tunnel.service; then
  systemctl --user restart skud-tunnel.service
fi

sleep 8
if ! curl -sf "http://127.0.0.1:${APP_PORT:-8001}/api/health" >/dev/null; then
  systemctl --user --no-pager --full status skud-backend.service skud-tunnel.service || true
  journalctl --user --no-pager -u skud-backend.service -n 100 || true
  journalctl --user --no-pager -u skud-tunnel.service -n 80 || true
  exit 1
fi
if [ -f "$DEPLOY_DIR/run/localhostrun.url" ]; then
  PUBLIC_URL="$(cat "$DEPLOY_DIR/run/localhostrun.url")"
  PUBLIC_URL_HEALTHY=false
  for _ in $(seq 1 18); do
    if curl -ksf "$PUBLIC_URL/api/health" >/dev/null; then
      PUBLIC_URL_HEALTHY=true
      break
    fi
    sleep 5
    PUBLIC_URL="$(cat "$DEPLOY_DIR/run/localhostrun.url")"
  done
  if [ "$PUBLIC_URL_HEALTHY" != true ]; then
    echo "Public tunnel URL did not become healthy: $PUBLIC_URL" >&2
    journalctl --user --no-pager -u skud-tunnel.service -n 120 || true
    exit 1
  fi
  echo "SKUD_PUBLIC_URL=$PUBLIC_URL"
  echo "::notice title=SKUD public URL::$PUBLIC_URL"
fi
if [ -n "${GOOGLE_SERVICE_ACCOUNT_FILE:-}" ]; then
  if [ -f "$GOOGLE_SERVICE_ACCOUNT_FILE" ]; then
    echo "::notice title=Google service account::configured"
  else
    echo "::warning title=Google service account missing::$GOOGLE_SERVICE_ACCOUNT_FILE"
  fi
fi
systemctl --user --no-pager --full status skud-backend.service skud-tunnel.service
