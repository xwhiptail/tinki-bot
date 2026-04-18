#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$PROJECT_ROOT/scripts/remote-common.sh"

RESTART_SERVICE="${1:-}"

remote_bash <<EOF
set -e
if [ "$RESTART_SERVICE" = "--restart-service" ]; then
  sudo systemctl restart tinki-bot
  sleep 5
fi
cd "$REMOTE_REPO_DIR"
/opt/apps/tinki-bot/myenv/bin/python scripts/check_awscost.py
EOF
