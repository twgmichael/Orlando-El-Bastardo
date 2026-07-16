#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="${OEB_WORKER_SCREEN_SESSION:-oeb-worker}"
HARNESS_URL="${OEB_HARNESS_URL:-http://127.0.0.1:8088}"
ADMIN_TOKEN="${API_ADMIN_TOKEN:-local-admin-token}"

sessions="$(screen -ls 2>/dev/null | awk -v name=".$SESSION_NAME" '$1 ~ name {print $1}' || true)"

if [ -n "$sessions" ]; then
  echo "screen: running ($SESSION_NAME)"
  echo "$sessions"
else
  echo "screen: not running ($SESSION_NAME)"
fi

if command -v curl >/dev/null 2>&1; then
  echo "harness state:"
  curl -sS -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$HARNESS_URL/api/v1/debug/studio-state" || true
  echo
else
  echo "curl not found; skipping harness state."
fi
