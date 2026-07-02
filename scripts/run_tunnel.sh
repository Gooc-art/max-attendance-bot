#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/run"
ENV_FILE="$ROOT_DIR/.env"
REGISTER_SCRIPT="$ROOT_DIR/scripts/register_max_webhook.py"
ENV_HELPER="$ROOT_DIR/scripts/set_env_value.py"

mkdir -p "$LOG_DIR" "$RUN_DIR"

if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

APP_PORT="${APP_PORT:-8001}"
PUBLIC_URL_FILE="$RUN_DIR/localhostrun.url"
TUNNEL_LOG="$LOG_DIR/localhostrun.log"
REGISTER_LOG="$LOG_DIR/webhook-register.log"

log_line() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$TUNNEL_LOG"
}

case "${SKUD_DISABLE_TUNNEL:-false}" in
  1|true|TRUE|yes|YES)
    log_line "localhost.run tunnel disabled by SKUD_DISABLE_TUNNEL"
    exit 0
    ;;
esac

register_webhook() {
  local public_url="$1"
  local webhook_url="${public_url%/}/api/webhooks/max"
  "$ROOT_DIR/.venv/bin/python3" "$ENV_HELPER" "$ENV_FILE" "MAX_BOT_WEBHOOK_URL" "$webhook_url"
  MAX_BOT_WEBHOOK_URL="$webhook_url" "$ROOT_DIR/.venv/bin/python3" "$REGISTER_SCRIPT" >> "$REGISTER_LOG" 2>&1
}

while true; do
  log_line "starting localhost.run tunnel on port $APP_PORT"

  ssh -o StrictHostKeyChecking=no \
      -o ServerAliveInterval=30 \
      -o ServerAliveCountMax=3 \
      -o ExitOnForwardFailure=yes \
      -R 80:127.0.0.1:"$APP_PORT" \
      nokey@localhost.run 2>&1 | while IFS= read -r line; do
    [ -n "$line" ] && log_line "$line"
    public_url="$(printf '%s\n' "$line" | grep -Eo 'https://[[:alnum:].-]+\.lhr\.life' | head -n 1 || true)"
    if [ -n "$public_url" ]; then
      current_url="$(cat "$PUBLIC_URL_FILE" 2>/dev/null || true)"
      if [ "$current_url" != "$public_url" ]; then
        printf '%s\n' "$public_url" > "$PUBLIC_URL_FILE"
        log_line "detected public url $public_url"
      fi
      register_webhook "$public_url" || log_line "failed to register webhook for $public_url"
    fi
  done

  log_line "tunnel process exited, retrying in 5 seconds"
  sleep 5
done
