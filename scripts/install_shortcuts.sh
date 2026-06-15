#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/skud" <<EOF
#!/bin/bash
cd "$ROOT_DIR" || exit 1
exec "\${SHELL:-/bin/bash}" -l
EOF

cat > "$BIN_DIR/cskud" <<EOF
#!/bin/bash
cd "$ROOT_DIR" || exit 1
exec "\${SHELL:-/bin/bash}" -l
EOF

cat > "$BIN_DIR/skudvenv" <<EOF
#!/bin/bash
cd "$ROOT_DIR" || exit 1
if [ -d "$ROOT_DIR/.venv" ]; then
  export VIRTUAL_ENV="$ROOT_DIR/.venv"
  export PATH="$ROOT_DIR/.venv/bin:\$PATH"
fi
exec "\${SHELL:-/bin/bash}" -l
EOF

cat > "$BIN_DIR/skudlogs" <<EOF
#!/bin/bash
tail -f "$ROOT_DIR/logs/backend.stderr.log"
EOF

cat > "$BIN_DIR/skudurl" <<EOF
#!/bin/bash
cat "$ROOT_DIR/run/localhostrun.url"
EOF

chmod +x \
  "$BIN_DIR/skud" \
  "$BIN_DIR/cskud" \
  "$BIN_DIR/skudvenv" \
  "$BIN_DIR/skudlogs" \
  "$BIN_DIR/skudurl"

echo "installed shortcuts into $BIN_DIR"
