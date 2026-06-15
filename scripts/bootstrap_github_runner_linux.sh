#!/bin/bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Gooc-art/max-attendance-bot}"
RUNNER_TOKEN="${RUNNER_TOKEN:-}"
RUNNER_NAME="${RUNNER_NAME:-skud-prod-$(hostname)}"
RUNNER_LABELS="${RUNNER_LABELS:-skud-prod}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner-skud}"
RUNNER_VERSION="${RUNNER_VERSION:-2.328.0}"

if [ -z "$RUNNER_TOKEN" ]; then
  echo "RUNNER_TOKEN is required" >&2
  exit 1
fi

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y curl git rsync python3 python3-venv python3-pip openssh-client ca-certificates
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y curl git rsync python3 python3-pip openssh-clients ca-certificates
else
  echo "Install curl, git, rsync, python3, python3-venv, pip, and openssh-client manually, then rerun." >&2
  exit 1
fi

sudo loginctl enable-linger "$(id -un)"

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) RUNNER_ARCH="x64" ;;
  aarch64|arm64) RUNNER_ARCH="arm64" ;;
  *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
esac

RUNNER_TARBALL="actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"
curl -L -o "$RUNNER_TARBALL" "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_TARBALL}"
tar xzf "$RUNNER_TARBALL"
rm -f "$RUNNER_TARBALL"

./config.sh \
  --url "$REPO_URL" \
  --token "$RUNNER_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS" \
  --unattended \
  --replace

sudo ./svc.sh install "$(id -un)"
sudo ./svc.sh start
sudo ./svc.sh status
