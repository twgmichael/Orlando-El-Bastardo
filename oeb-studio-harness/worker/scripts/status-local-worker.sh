#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="${OEB_WORKER_SCREEN_SESSION:-oeb-worker}"
HARNESS_URL="${OEB_HARNESS_URL:-http://127.0.0.1:8088}"
ADMIN_TOKEN="${API_ADMIN_TOKEN:-local-admin-token}"

if screen -ls | grep -q "[.]$SESSION_NAME[[:space:]]"; then
  echo "screen: running ($SESSION_NAME)"
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
