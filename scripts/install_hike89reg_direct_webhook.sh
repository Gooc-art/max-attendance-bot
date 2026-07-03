#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOMAIN="${SKUD_WEBHOOK_DOMAIN:-89-150-35-139.sslip.io}"
APP_PORT="${APP_PORT:-8001}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/conf.d/skud-webhook.conf}"
WEBROOT="${SKUD_CERTBOT_WEBROOT:-/var/www/letsencrypt}"
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo env SKUD_WEBHOOK_DOMAIN=$DOMAIN bash $0" >&2
  exit 1
fi

if ! command -v nginx >/dev/null 2>&1 || ! command -v certbot >/dev/null 2>&1; then
  apt-get update
  apt-get install -y nginx certbot
fi

mkdir -p "$WEBROOT/.well-known/acme-challenge"
if [ -f "$NGINX_CONF" ]; then
  cp "$NGINX_CONF" "$NGINX_CONF.bak.$(date +%Y%m%d%H%M%S)"
fi

write_http_config() {
  cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    location ^~ /.well-known/acme-challenge/ {
        root $WEBROOT;
        default_type text/plain;
        try_files \$uri =404;
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

    location = /api/webhooks/max {
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
}

write_https_config() {
  cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    location ^~ /.well-known/acme-challenge/ {
        root $WEBROOT;
        default_type text/plain;
        try_files \$uri =404;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN;

    ssl_certificate $CERT_DIR/fullchain.pem;
    ssl_certificate_key $CERT_DIR/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location = /api/health {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 10s;
    }

    location = /api/webhooks/max {
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
}

write_http_config
nginx -t
systemctl reload nginx

printf 'ok\n' > "$WEBROOT/.well-known/acme-challenge/skud-test"
curl -fsS "http://$DOMAIN/.well-known/acme-challenge/skud-test" | grep -qx ok
curl -fsS "http://$DOMAIN/api/health" >/dev/null

certbot certonly \
  --webroot \
  --webroot-path "$WEBROOT" \
  --non-interactive \
  --agree-tos \
  --register-unsafely-without-email \
  -d "$DOMAIN"

write_https_config
nginx -t
systemctl reload nginx

curl -fsS "https://$DOMAIN/api/health" >/dev/null

"$ROOT_DIR/.venv/bin/python3" "$ROOT_DIR/scripts/set_env_value.py" "$ROOT_DIR/.env" "SKUD_DISABLE_TUNNEL" "true"
"$ROOT_DIR/.venv/bin/python3" "$ROOT_DIR/scripts/register_max_webhook.py" --url "https://$DOMAIN"

systemctl --user stop skud-tunnel.service || true

echo "Direct MAX webhook is ready: https://$DOMAIN/api/webhooks/max"
