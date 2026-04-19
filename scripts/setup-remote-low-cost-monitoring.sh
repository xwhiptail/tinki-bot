#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$PROJECT_ROOT/scripts/remote-common.sh"

REMOTE_ARGS=""
if [[ $# -gt 0 ]]; then
  printf -v REMOTE_ARGS '%q ' "$@"
fi

remote_bash <<EOF
set -e
cd "$REMOTE_REPO_DIR"
/opt/apps/tinki-bot/myenv/bin/python scripts/setup_low_cost_monitoring.py $REMOTE_ARGS
EOF
