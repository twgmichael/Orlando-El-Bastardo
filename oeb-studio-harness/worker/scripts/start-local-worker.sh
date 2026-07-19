#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="${OEB_WORKER_SCREEN_SESSION:-oeb-worker}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$WORKER_DIR/../.." && pwd)"
LOG_FILE="${OEB_WORKER_LOG_FILE:-/tmp/oeb-harness-worker.log}"
WORKER_CONFIG="${OEB_WORKER_CONFIG:-config-examples/render-mac-01.yml}"

if [ -f "$WORKER_DIR/.env.local" ]; then
  # shellcheck disable=SC1091
  source "$WORKER_DIR/.env.local"
fi

export OEB_HARNESS_URL="${OEB_HARNESS_URL:-http://127.0.0.1:8088}"
export OEB_ENROLLMENT_TOKEN="${OEB_ENROLLMENT_TOKEN:-local-worker-enrollment-token}"
export OEB_WORKSPACE_ROOT="${OEB_WORKSPACE_ROOT:-$REPO_ROOT}"

if [ -z "${OEB_OUTPUT_ROOT:-}" ]; then
  echo "OEB_OUTPUT_ROOT is required." >&2
  echo "Set it in the shell or in $WORKER_DIR/.env.local." >&2
  exit 1
fi

export OEB_ARTIFACT_STORE_ROOT="${OEB_ARTIFACT_STORE_ROOT:-$OEB_OUTPUT_ROOT/oeb-studio-harness/artifacts}"

case "$OEB_OUTPUT_ROOT" in
  /tmp|/tmp/*|/private/tmp|/private/tmp/*)
    echo "Refusing to use temporary storage for OEB_OUTPUT_ROOT: $OEB_OUTPUT_ROOT" >&2
    echo "Mount OEB-PROJECT or set OEB_OUTPUT_ROOT to a durable project path." >&2
    exit 1
    ;;
esac

if [ ! -d "$OEB_OUTPUT_ROOT" ]; then
  echo "OEB_OUTPUT_ROOT does not exist: $OEB_OUTPUT_ROOT" >&2
  echo "Mount the project drive or set OEB_OUTPUT_ROOT to a durable project path." >&2
  exit 1
fi

if ! command -v screen >/dev/null 2>&1; then
  echo "screen is required to run the local worker detached." >&2
  exit 1
fi

if [ ! -x "$WORKER_DIR/.venv/bin/python" ]; then
  echo "Worker virtualenv not found at $WORKER_DIR/.venv/bin/python" >&2
  echo "Create it from $WORKER_DIR and install requirements first." >&2
  exit 1
fi

if [ ! -f "$WORKER_DIR/$WORKER_CONFIG" ]; then
  echo "Worker config not found: $WORKER_DIR/$WORKER_CONFIG" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")" "$OEB_OUTPUT_ROOT" "$OEB_ARTIFACT_STORE_ROOT"

existing_sessions="$(screen -ls 2>/dev/null | awk -v name=".$SESSION_NAME" '$1 ~ name {print $1}' || true)"
if [ -n "$existing_sessions" ]; then
  echo "Worker screen session already running: $SESSION_NAME"
  echo "$existing_sessions"
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
  echo \"\$(date '+%Y-%m-%d %H:%M:%S') starting OEB worker with $WORKER_CONFIG\" >> '$LOG_FILE'
  exec .venv/bin/python -u -m agent.main '$WORKER_CONFIG' >> '$LOG_FILE' 2>&1
"

echo "Started local worker in screen session: $SESSION_NAME"
echo "Harness: $OEB_HARNESS_URL"
echo "Config: $WORKER_CONFIG"
echo "Output root: $OEB_OUTPUT_ROOT"
echo "Artifact root: $OEB_ARTIFACT_STORE_ROOT"
echo "Log: $LOG_FILE"
