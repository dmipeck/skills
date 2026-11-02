#!/usr/bin/env bash
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "gh: not installed" >&2
  exit 127
fi

exec gh auth status "$@"
