#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="${OEB_WORKER_SCREEN_SESSION:-oeb-worker}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$WORKER_DIR/../.." && pwd)"
LOG_FILE="${OEB_WORKER_LOG_FILE:-/tmp/oeb-harness-worker.log}"

export OEB_HARNESS_URL="${OEB_HARNESS_URL:-http://127.0.0.1:8088}"
export OEB_ENROLLMENT_TOKEN="${OEB_ENROLLMENT_TOKEN:-local-worker-enrollment-token}"
export OEB_OUTPUT_ROOT="${OEB_OUTPUT_ROOT:-/tmp/oeb-harness-worker-output}"
export OEB_ARTIFACT_STORE_ROOT="${OEB_ARTIFACT_STORE_ROOT:-/tmp/oeb-harness-worker-artifacts}"
export OEB_WORKSPACE_ROOT="${OEB_WORKSPACE_ROOT:-$REPO_ROOT}"

if ! command -v screen >/dev/null 2>&1; then
  echo "screen is required to run the local worker detached." >&2
  exit 1
fi

if [ ! -x "$WORKER_DIR/.venv/bin/python" ]; then
  echo "Worker virtualenv not found at $WORKER_DIR/.venv/bin/python" >&2
  echo "Create it from $WORKER_DIR and install requirements first." >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")" "$OEB_OUTPUT_ROOT" "$OEB_ARTIFACT_STORE_ROOT"

if screen -ls | grep -q "[.]$SESSION_NAME[[:space:]]"; then
  echo "Worker screen session already running: $SESSION_NAME"
  exit 0
fi

screen -dmS "$SESSION_NAME" bash -lc "
  cd '$WORKER_DIR'
  export OEB_HARNESS_URL='$OEB_HARNESS_URL'
  export OEB_ENROLLMENT_TOKEN='$OEB_ENROLLMENT_TOKEN'
  export OEB_OUTPUT_ROOT='$OEB_OUTPUT_ROOT'
  export OEB_ARTIFACT_STORE_ROOT='$OEB_ARTIFACT_STORE_ROOT'
  export OEB_WORKSPACE_ROOT='$OEB_WORKSPACE_ROOT'
  export PYTHONPATH=.
  exec .venv/bin/python -u -m agent.main config-examples/mac-mini.yml >> '$LOG_FILE' 2>&1
"

echo "Started local worker in screen session: $SESSION_NAME"
echo "Harness: $OEB_HARNESS_URL"
echo "Output root: $OEB_OUTPUT_ROOT"
echo "Artifact root: $OEB_ARTIFACT_STORE_ROOT"
echo "Log: $LOG_FILE"
