#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/run"
ENV_FILE="$ROOT_DIR/.env"
ENV_HELPER="$ROOT_DIR/scripts/set_env_value.py"

mkdir -p "$LOG_DIR" "$RUN_DIR"

if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

APP_PORT="${APP_PORT:-8001}"
PUBLIC_URL_FILE="$RUN_DIR/public_url_tunnel.url"
TUNNEL_LOG="$LOG_DIR/public-url-tunnel.log"

log_line() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$TUNNEL_LOG"
}

while true; do
  log_line "starting public url tunnel on port $APP_PORT"

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
      current_env_url="$(grep -E '^PUBLIC_BASE_URL=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
      if [ "$current_url" != "$public_url" ] || [ "$current_env_url" != "$public_url" ]; then
        printf '%s\n' "$public_url" > "$PUBLIC_URL_FILE"
        "$ROOT_DIR/.venv/bin/python3" "$ENV_HELPER" "$ENV_FILE" "PUBLIC_BASE_URL" "$public_url"
        log_line "detected public url $public_url"
        systemctl --user restart skud-backend.service || log_line "failed to restart backend after public url update"
      fi
    fi
  done

  log_line "public url tunnel process exited, retrying in 5 seconds"
  sleep 5
done
