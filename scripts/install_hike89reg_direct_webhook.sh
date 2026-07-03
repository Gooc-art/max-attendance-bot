#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOMAIN="${SKUD_WEBHOOK_DOMAIN:-hike89reg.fvds.ru}"
APP_PORT="${APP_PORT:-8001}"
NGINX_CONF="/etc/nginx/conf.d/hike89reg-monitoring.conf"
CERTBOT_WEBROOT="/var/www/certbot"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo env SKUD_WEBHOOK_DOMAIN=$DOMAIN bash $0" >&2
  exit 1
fi

if [ ! -f "$NGINX_CONF" ]; then
  echo "Missing nginx config: $NGINX_CONF" >&2
  exit 1
fi

mkdir -p "$CERTBOT_WEBROOT/.well-known/acme-challenge"
cp "$NGINX_CONF" "$NGINX_CONF.bak.$(date +%Y%m%d%H%M%S)"

python3 - "$NGINX_CONF" "$APP_PORT" "$CERTBOT_WEBROOT" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

path = Path(sys.argv[1])
port = sys.argv[2]
webroot = sys.argv[3]
text = path.read_text()

managed = f"""
    # SKUD direct MAX webhook.
    location ^~ /.well-known/acme-challenge/ {{
        root {webroot};
        default_type "text/plain";
        try_files $uri =404;
    }}

    location = /api/health {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 10s;
    }}

    location = /api/webhooks/max {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 10s;
    }}
"""

if "SKUD direct MAX webhook" in text:
    start = text.index("    # SKUD direct MAX webhook.")
    next_location = text.index("\n    location / {", start)
    text = text[:start] + managed + text[next_location:]
else:
    marker = "\n    location / {"
    if marker not in text:
        raise SystemExit("Cannot find main location block to insert SKUD locations")
    text = text.replace(marker, managed + marker, 1)

path.write_text(text)
PY

nginx -t
systemctl reload nginx

printf 'ok\n' > "$CERTBOT_WEBROOT/.well-known/acme-challenge/skud-test"
curl -fsS "http://$DOMAIN/.well-known/acme-challenge/skud-test" | grep -qx ok
curl -fsS "http://$DOMAIN/api/health" >/dev/null

if command -v certbot >/dev/null 2>&1; then
  certbot --nginx \
    --non-interactive \
    --agree-tos \
    --register-unsafely-without-email \
    --redirect \
    -d "$DOMAIN"
else
  apt-get update
  apt-get install -y certbot python3-certbot-nginx
  certbot --nginx \
    --non-interactive \
    --agree-tos \
    --register-unsafely-without-email \
    --redirect \
    -d "$DOMAIN"
fi

nginx -t
systemctl reload nginx

curl -fsS "https://$DOMAIN/api/health" >/dev/null

"$ROOT_DIR/.venv/bin/python3" "$ROOT_DIR/scripts/set_env_value.py" "$ROOT_DIR/.env" "SKUD_DISABLE_TUNNEL" "true"
"$ROOT_DIR/.venv/bin/python3" "$ROOT_DIR/scripts/register_max_webhook.py" --url "https://$DOMAIN"

systemctl --user stop skud-tunnel.service || true

echo "Direct MAX webhook is ready: https://$DOMAIN/api/webhooks/max"
