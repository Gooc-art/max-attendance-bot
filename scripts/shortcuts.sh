#!/bin/bash

SKUD_ROOT="${SKUD_ROOT:-$HOME/skud}"

cskud() {
  cd "$SKUD_ROOT"
}

skudvenv() {
  cd "$SKUD_ROOT" || return 1
  if [ -f .venv/bin/activate ]; then
    . .venv/bin/activate
  fi
}

skudlogs() {
  tail -f "$SKUD_ROOT/logs/backend.stderr.log"
}

skudurl() {
  cat "$SKUD_ROOT/run/localhostrun.url"
}

skudshell() {
  cd "$SKUD_ROOT" || return 1
  exec "${SHELL:-/bin/bash}" -l
}
