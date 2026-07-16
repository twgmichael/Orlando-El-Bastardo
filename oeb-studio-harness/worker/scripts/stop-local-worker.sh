#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="${OEB_WORKER_SCREEN_SESSION:-oeb-worker}"

if screen -ls | grep -q "[.]$SESSION_NAME[[:space:]]"; then
  screen -S "$SESSION_NAME" -X quit
  echo "Stopped local worker screen session: $SESSION_NAME"
else
  echo "No local worker screen session found: $SESSION_NAME"
fi
