#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_HOST="${1:-godmod-macmini}"
REMOTE_DIR="${2:-/Users/goocbk.ru/skud/}"

rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.env' \
  --exclude 'data/' \
  --exclude 'logs/' \
  --exclude 'run/' \
  "$ROOT_DIR/" \
  "${REMOTE_HOST}:${REMOTE_DIR}"
