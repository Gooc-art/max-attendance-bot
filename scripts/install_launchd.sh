#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/run"
BACKEND_LABEL="com.gooc.attendancebot.backend"
TUNNEL_LABEL="com.gooc.attendancebot.tunnel"
BACKEND_PLIST="$AGENTS_DIR/$BACKEND_LABEL.plist"
TUNNEL_PLIST="$AGENTS_DIR/$TUNNEL_LABEL.plist"

mkdir -p "$AGENTS_DIR" "$LOG_DIR" "$RUN_DIR"
chmod +x "$ROOT_DIR/scripts/run_backend.sh" "$ROOT_DIR/scripts/run_tunnel.sh"

cat > "$BACKEND_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$BACKEND_LABEL</string>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT_DIR/scripts/run_backend.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/backend.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/backend.stderr.log</string>
</dict>
</plist>
EOF

cat > "$TUNNEL_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$TUNNEL_LABEL</string>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT_DIR/scripts/run_tunnel.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/tunnel.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/tunnel.stderr.log</string>
</dict>
</plist>
EOF

launchctl unload "$BACKEND_PLIST" >/dev/null 2>&1 || true
launchctl unload "$TUNNEL_PLIST" >/dev/null 2>&1 || true

launchctl load "$BACKEND_PLIST"
launchctl load "$TUNNEL_PLIST"

echo "installed $BACKEND_LABEL"
echo "installed $TUNNEL_LABEL"
