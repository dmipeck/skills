#!/usr/bin/env bash
set -euo pipefail

if ! command -v glab >/dev/null 2>&1; then
  echo "glab: not installed" >&2
  exit 127
fi

exec glab auth status "$@"
