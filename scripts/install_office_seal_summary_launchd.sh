#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$ROOT_DIR/logs"

mkdir -p "$AGENTS_DIR" "$LOG_DIR"

for old_label in \
  "com.gooc.attendancebot.office-seal-reminder-initial" \
  "com.gooc.attendancebot.office-seal-reminder-final" \
  "com.gooc.attendancebot.office-seal-summary"; do
  old_plist="$AGENTS_DIR/$old_label.plist"
  launchctl unload "$old_plist" >/dev/null 2>&1 || true
  rm -f "$old_plist"
done

install_job() {
  local label="$1"
  local hour="$2"
  local minute="$3"
  local command="$4"
  local plist="$AGENTS_DIR/$label.plist"

  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$label</string>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd "$ROOT_DIR" &amp;&amp; $command</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>$hour</integer>
    <key>Minute</key>
    <integer>$minute</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/$label.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/$label.stderr.log</string>
</dict>
</plist>
EOF

  launchctl unload "$plist" >/dev/null 2>&1 || true
  launchctl load "$plist"
  echo "installed $label"
}

install_job \
  "com.gooc.attendancebot.office-seal-reminder-female" \
  17 \
  10 \
  "\"$ROOT_DIR/.venv/bin/python3\" \"$ROOT_DIR/scripts/send_office_seal_reminders.py\" female"

install_job \
  "com.gooc.attendancebot.office-seal-reminder-male" \
  17 \
  55 \
  "\"$ROOT_DIR/.venv/bin/python3\" \"$ROOT_DIR/scripts/send_office_seal_reminders.py\" male"
