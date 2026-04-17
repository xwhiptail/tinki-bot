#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_CONFIG_PATH="$PROJECT_ROOT/deploy-ec2.local.sh"

SERVER_HOST="${TINKI_EC2_HOST:-}"
USER_NAME="${TINKI_EC2_USER:-ec2-user}"
KEY_PATH="${TINKI_EC2_KEY_PATH:-}"
REMOTE_REPO_DIR="${TINKI_EC2_REPO_DIR:-/opt/apps/tinki-bot/repo}"
REMOTE_DATA_DIR="${TINKI_EC2_DATA_DIR:-/opt/apps/tinki-bot/data}"

if [[ -f "$LOCAL_CONFIG_PATH" ]]; then
  # shellcheck disable=SC1090
  source "$LOCAL_CONFIG_PATH"
fi

if [[ -z "${SERVER_HOST:-}" ]]; then
  echo "Set SERVER_HOST in deploy-ec2.local.sh or TINKI_EC2_HOST in your shell environment." >&2
  exit 1
fi

SSH_TARGET="${USER_NAME}@${SERVER_HOST}"
SSH_ARGS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)
if [[ -n "${KEY_PATH:-}" ]]; then
  SSH_ARGS+=(-i "$KEY_PATH")
fi

remote_ssh() {
  ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "$@"
}

remote_bash() {
  local script
  script="$(cat)"
  ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "bash -s" <<<"$script"
}

remote_copy() {
  local source_path="$1"
  local remote_path="$2"
  local recursive="${3:-false}"
  local scp_args=("${SSH_ARGS[@]}")

  if [[ "$recursive" == "true" ]]; then
    scp_args+=(-r)
  fi

  scp "${scp_args[@]}" "$source_path" "${SSH_TARGET}:${remote_path}"
}
