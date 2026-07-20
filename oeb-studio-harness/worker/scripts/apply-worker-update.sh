#!/usr/bin/env bash
set -euo pipefail

TARGET_GIT_SHA=""
SERVICE_NAME=""
RESTART_SERVICE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_GIT_SHA="${2:-}"
      shift 2
      ;;
    --service)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    --restart-service)
      RESTART_SERVICE=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ ! -d .git ]]; then
  echo "Run from the worker workspace root containing .git" >&2
  exit 2
fi

git fetch origin --prune

if [[ -n "$TARGET_GIT_SHA" ]]; then
  git reset --hard "$TARGET_GIT_SHA"
else
  CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "$CURRENT_BRANCH" == "HEAD" ]]; then
    git reset --hard origin/main
  else
    git reset --hard "origin/$CURRENT_BRANCH"
  fi
fi

python -m compileall -q oeb-studio-harness/worker/agent

if [[ "$RESTART_SERVICE" == "1" ]]; then
  if [[ -z "$SERVICE_NAME" ]]; then
    echo "--service is required with --restart-service" >&2
    exit 2
  fi
  sudo systemctl restart --no-block "$SERVICE_NAME"
fi
