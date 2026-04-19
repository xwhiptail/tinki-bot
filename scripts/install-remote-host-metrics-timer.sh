#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$PROJECT_ROOT/scripts/remote-common.sh"

remote_bash <<EOF
set -e
cd "$REMOTE_REPO_DIR"
sudo bash scripts/install_host_metrics_timer.sh
EOF
