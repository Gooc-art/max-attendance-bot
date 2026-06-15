#!/bin/bash
set -euo pipefail

USER_HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
USER_HOME="${USER_HOME:-$HOME}"
ROOT_DIR="${SKUD_DEPLOY_DIR:-$USER_HOME/skud}"
SYSTEMD_USER_DIR="$USER_HOME/.config/systemd/user"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

mkdir -p "$SYSTEMD_USER_DIR" "$ROOT_DIR/logs" "$ROOT_DIR/run" "$ROOT_DIR/data"

cat > "$SYSTEMD_USER_DIR/skud-backend.service" <<EOF
[Unit]
Description=SKUD MAX bot backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
ExecStart=$ROOT_DIR/scripts/run_backend.sh
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

cat > "$SYSTEMD_USER_DIR/skud-tunnel.service" <<EOF
[Unit]
Description=SKUD MAX bot localhost.run tunnel
After=network-online.target skud-backend.service
Wants=network-online.target
Requires=skud-backend.service

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
ExecStart=$ROOT_DIR/scripts/run_tunnel.sh
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable skud-backend.service skud-tunnel.service
