#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

WORKERS="${WORKERS:-500}"
TIMEOUT="${TIMEOUT:-6}"
FAST_MS="${FAST_MS:-3000}"
LIMIT="${LIMIT:-0}"

args=(
  --collect
  --check
  --workers "$WORKERS"
  --timeout "$TIMEOUT"
  --fast-ms "$FAST_MS"
)

if [[ "$LIMIT" != "0" ]]; then
  args+=(--limit "$LIMIT")
fi

printf '[run] workers=%s timeout=%s fast_ms=%s limit=%s\n' "$WORKERS" "$TIMEOUT" "$FAST_MS" "$LIMIT"
python3 ./check_socks5.py "${args[@]}"
