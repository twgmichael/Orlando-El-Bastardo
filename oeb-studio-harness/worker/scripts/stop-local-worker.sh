#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="${OEB_WORKER_SCREEN_SESSION:-oeb-worker}"

sessions="$(screen -ls 2>/dev/null | awk -v name=".$SESSION_NAME" '$1 ~ name {print $1}' || true)"

if [ -z "$sessions" ]; then
  echo "No local worker screen session found: $SESSION_NAME"
  exit 0
fi

for session in $sessions; do
  screen -S "$session" -X quit
  echo "Stopped local worker screen session: $session"
done
