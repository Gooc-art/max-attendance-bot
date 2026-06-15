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
  "$SOURCE_DIR/" \
  "$DEPLOY_DIR/"

mkdir -p "$DEPLOY_DIR/data" "$DEPLOY_DIR/logs" "$DEPLOY_DIR/run"

cd "$DEPLOY_DIR"
if [ -f .env ]; then
  set -a
  . .env
  set +a
fi
"$PYTHON_BIN" -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

chmod +x scripts/*.sh
bash scripts/install_systemd_user_linux.sh

systemctl --user restart skud-backend.service
systemctl --user restart skud-tunnel.service

sleep 3
curl -sf "http://127.0.0.1:${APP_PORT:-8001}/api/health" >/dev/null
systemctl --user --no-pager --full status skud-backend.service skud-tunnel.service
