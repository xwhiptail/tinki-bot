#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$PROJECT_ROOT/scripts/remote-common.sh"

remote_bash <<EOF
cd "$REMOTE_REPO_DIR"
/opt/apps/tinki-bot/myenv/bin/python -m pytest -q
EOF
