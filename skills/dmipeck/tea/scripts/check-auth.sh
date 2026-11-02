#!/usr/bin/env bash
set -euo pipefail

if ! command -v tea >/dev/null 2>&1; then
  echo "tea: not installed" >&2
  exit 127
fi

exec tea logins status "$@"
