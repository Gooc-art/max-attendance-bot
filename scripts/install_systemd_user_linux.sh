#!/bin/bash
set -euo pipefail

USER_HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
USER_HOME="${USER_HOME:-$HOME}"
ROOT_DIR="${SKUD_DEPLOY_DIR:-$USER_HOME/skud}"
SYSTEMD_USER_DIR="$USER_HOME/.config/systemd/user"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

if ! mkdir -p "$SYSTEMD_USER_DIR" "$ROOT_DIR/logs" "$ROOT_DIR/run" "$ROOT_DIR/data" 2>/dev/null; then
  sudo mkdir -p "$SYSTEMD_USER_DIR" "$ROOT_DIR/logs" "$ROOT_DIR/run" "$ROOT_DIR/data"
  sudo chown -R "$(id -u):$(id -g)" "$USER_HOME/.config" "$ROOT_DIR"
fi
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

install_office_seal_reminder() {
  local gender="$1"
  local hour="$2"
  local minute="$3"
  local name="skud-office-seal-reminder-$gender"

  cat > "$SYSTEMD_USER_DIR/$name.service" <<EOF
[Unit]
Description=SKUD office seal reminder ($gender)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT_DIR
ExecStart=$ROOT_DIR/.venv/bin/python3 $ROOT_DIR/scripts/send_office_seal_reminders.py $gender
Environment=PYTHONUNBUFFERED=1
EOF

  cat > "$SYSTEMD_USER_DIR/$name.timer" <<EOF
[Unit]
Description=SKUD office seal reminder timer ($gender)

[Timer]
OnCalendar=Mon..Fri *-*-* $hour:$minute:00
AccuracySec=1min
Unit=$name.service

[Install]
WantedBy=timers.target
EOF
}

install_office_seal_reminder female 17 10
install_office_seal_reminder male 17 55

systemctl --user daemon-reload
systemctl --user enable skud-backend.service skud-tunnel.service
systemctl --user enable --now skud-office-seal-reminder-female.timer skud-office-seal-reminder-male.timer
