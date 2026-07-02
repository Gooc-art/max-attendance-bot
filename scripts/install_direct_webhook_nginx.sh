#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOMAIN="${SKUD_WEBHOOK_DOMAIN:-89-150-35-139.sslip.io}"
APP_PORT="${APP_PORT:-8001}"
NGINX_CONF="/etc/nginx/conf.d/skud-webhook.conf"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo env SKUD_WEBHOOK_DOMAIN=$DOMAIN bash $0" >&2
  exit 1
fi

if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx is required" >&2
  exit 1
fi

if ! command -v certbot >/dev/null 2>&1; then
  apt-get update
  apt-get install -y certbot python3-certbot-nginx
fi

cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    location /api/webhooks/max {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 10s;
    }

    location = /api/health {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 10s;
    }
}
EOF

nginx -t
systemctl reload nginx

certbot --nginx \
  --non-interactive \
  --agree-tos \
  --register-unsafely-without-email \
  --redirect \
  -d "$DOMAIN"

nginx -t
systemctl reload nginx

curl -fsS "https://$DOMAIN/api/health" >/dev/null

"$ROOT_DIR/.venv/bin/python3" "$ROOT_DIR/scripts/set_env_value.py" "$ROOT_DIR/.env" "SKUD_DISABLE_TUNNEL" "true"
"$ROOT_DIR/.venv/bin/python3" "$ROOT_DIR/scripts/register_max_webhook.py" --url "https://$DOMAIN"

echo "Direct MAX webhook is ready: https://$DOMAIN/api/webhooks/max"
