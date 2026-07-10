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
systemctl --user stop skud-tunnel.service || true
systemctl --user restart skud-polling.service

sleep 3
if ! systemctl --user is-active --quiet skud-polling.service; then
  systemctl --user --no-pager --full status skud-backend.service skud-polling.service skud-tunnel.service || true
  journalctl --user --no-pager -u skud-polling.service -n 100 || true
  exit 1
fi
if [ -n "${GOOGLE_SERVICE_ACCOUNT_FILE:-}" ]; then
  if [ -f "$GOOGLE_SERVICE_ACCOUNT_FILE" ]; then
    echo "::notice title=Google service account::configured"
    SHEETS_DIRECTORY_COUNT="$("$DEPLOY_DIR/.venv/bin/python3" - <<'PY'
from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService

service = GoogleSheetsDirectoryService.from_settings()
print(len(service.list_employees()))
PY
)"
    echo "::notice title=Google directory rows::$SHEETS_DIRECTORY_COUNT"
  else
    echo "::warning title=Google service account missing::$GOOGLE_SERVICE_ACCOUNT_FILE"
  fi
fi
systemctl --user --no-pager --full status skud-backend.service skud-polling.service skud-tunnel.service
