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
  local source_name remote_target_quoted

  source_name="$(basename "$source_path")"
  printf -v remote_target_quoted '%q' "${remote_path%/}/$source_name"

  if [[ "$recursive" == "true" ]]; then
    local source_dir
    source_dir="$(cd "$source_path" && pwd)"
    (
      cd "$source_dir"
      find . \( -type f -o -type l \) \
        ! -path '*/__pycache__/*' \
        ! -path '*/.pytest_cache/*' \
        ! -path '*/pytest-cache-files-*/*' \
        ! -name '._*' \
        ! -name '.DS_Store' \
        -print0 \
        | COPYFILE_DISABLE=1 tar --format=ustar -C "$source_dir" --null -T - -cf -
    ) \
      | ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "rm -rf ${remote_target_quoted} && mkdir -p ${remote_target_quoted} && tar -xmf - --no-same-permissions --no-overwrite-dir -C ${remote_target_quoted}"
    return
  fi

  ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "rm -f ${remote_target_quoted}"
  scp "${scp_args[@]}" "$source_path" "${SSH_TARGET}:${remote_path}"
}
