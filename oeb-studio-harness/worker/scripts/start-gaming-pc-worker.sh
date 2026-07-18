#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$WORKER_DIR/../.." && pwd)"
LOG_FILE="${OEB_WORKER_LOG_FILE:-/tmp/oeb-gaming-pc-worker.log}"

if [ -f "$WORKER_DIR/.env.local" ]; then
  # shellcheck disable=SC1091
  source "$WORKER_DIR/.env.local"
fi

export OEB_HARNESS_URL="${OEB_HARNESS_URL:-http://oeb-studio.docker-pi}"
export OEB_WORKSPACE_ROOT="${OEB_WORKSPACE_ROOT:-$REPO_ROOT}"
export OEB_OUTPUT_ROOT="${OEB_OUTPUT_ROOT:-/mnt/oeb-project/OEB-PRODUCTION}"
export OEB_ARTIFACT_STORE_ROOT="${OEB_ARTIFACT_STORE_ROOT:-$OEB_OUTPUT_ROOT/oeb-studio-harness/artifacts}"

case "$OEB_OUTPUT_ROOT" in
  /tmp|/tmp/*|/var/tmp|/var/tmp/*|/run|/run/*)
    echo "Refusing to use temporary storage for OEB_OUTPUT_ROOT: $OEB_OUTPUT_ROOT" >&2
    echo "Mount the external SSD and set OEB_OUTPUT_ROOT to its project output path." >&2
    exit 1
    ;;
esac

if [ ! -d "$OEB_OUTPUT_ROOT" ]; then
  echo "OEB_OUTPUT_ROOT does not exist: $OEB_OUTPUT_ROOT" >&2
  echo "Mount the external SSD or set OEB_OUTPUT_ROOT to a durable project path." >&2
  exit 1
fi

if ! command -v "${OEB_BLENDER_EXECUTABLE:-blender}" >/dev/null 2>&1; then
  echo "Blender executable not found: ${OEB_BLENDER_EXECUTABLE:-blender}" >&2
  echo "Install Blender or set OEB_BLENDER_EXECUTABLE." >&2
  exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama is not on PATH. Install Ollama before starting the gaming-PC worker." >&2
  exit 1
fi

if [ ! -x "$WORKER_DIR/.venv/bin/python" ]; then
  echo "Worker virtualenv not found at $WORKER_DIR/.venv/bin/python" >&2
  echo "Create it from $WORKER_DIR and install requirements first." >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")" "$OEB_OUTPUT_ROOT" "$OEB_ARTIFACT_STORE_ROOT"

cd "$WORKER_DIR"
export PYTHONPATH=.
exec .venv/bin/python -u -m agent.main config-examples/gaming-pc.yml 2>&1 | tee -a "$LOG_FILE"
