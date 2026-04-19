#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$PROJECT_ROOT/scripts/remote-common.sh"

REMOTE_NAME="origin"
LOCAL_COMMIT="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
REMOTE_URL="$(git -C "$PROJECT_ROOT" remote get-url "$REMOTE_NAME")"
GITHUB_COMMIT="$(git -C "$PROJECT_ROOT" ls-remote "$REMOTE_URL" refs/heads/main | awk '{print $1}')"

if [[ -z "$LOCAL_COMMIT" ]]; then
  echo "Unable to determine local git commit." >&2
  exit 1
fi

if [[ -z "$REMOTE_URL" || -z "$GITHUB_COMMIT" ]]; then
  echo "Unable to determine GitHub main commit from '$REMOTE_NAME'." >&2
  exit 1
fi

echo "Local HEAD:    ${LOCAL_COMMIT:0:7}"
echo "GitHub main:   ${GITHUB_COMMIT:0:7}"

if [[ "$LOCAL_COMMIT" != "$GITHUB_COMMIT" ]]; then
  echo "Local HEAD does not match GitHub main. Pull/push first so deploy matches GitHub." >&2
  exit 1
fi

REPO_FILES=(
  "tinki-bot.py"
  "config.py"
  "README.md"
  "INSTALL.md"
  "CLAUDE.md"
  "AGENTS.md"
  "requirements.txt"
  "pytest.ini"
  ".env.example"
  ".gitignore"
)

REPO_DIRS=("utils" "cogs" "tests" "scripts")

remote_bash <<EOF
set -e
ts=\$(date +%Y%m%d_%H%M%S)
backup_dir=/opt/apps/tinki-bot/backup
mkdir -p "\$backup_dir"
if [ -f "$REMOTE_REPO_DIR/tinki-bot.py" ]; then
  cp "$REMOTE_REPO_DIR/tinki-bot.py" "$REMOTE_REPO_DIR/tinki-bot.py.backup_\$ts"
fi
if [ -d "$REMOTE_DATA_DIR" ]; then
  tar -czf "\$backup_dir/data_backup_\$ts.tar.gz" -C /opt/apps/tinki-bot data
fi
ls -1t "$REMOTE_REPO_DIR"/tinki-bot.py.backup_* 2>/dev/null | tail -n +4 | xargs -r rm --
ls -1t "\$backup_dir"/data_backup_*.tar.gz 2>/dev/null | tail -n +4 | xargs -r rm --
EOF

DEPLOYED_COMMIT="$(remote_bash <<EOF
if [ -f "$REMOTE_REPO_DIR/.deploy-commit" ]; then
  cat "$REMOTE_REPO_DIR/.deploy-commit"
fi
EOF
)"

if [[ -n "$DEPLOYED_COMMIT" ]]; then
  echo "Deployed now:  ${DEPLOYED_COMMIT:0:7}"
else
  echo "Deployed now:  unknown"
fi

remote_bash <<EOF
mkdir -p $(printf "%q " "$REMOTE_REPO_DIR")
mkdir -p $(printf "%q " "$REMOTE_REPO_DIR/utils" "$REMOTE_REPO_DIR/cogs" "$REMOTE_REPO_DIR/tests" "$REMOTE_REPO_DIR/assets" "$REMOTE_REPO_DIR/scripts")
EOF

for file in "${REPO_FILES[@]}"; do
  remote_copy "$PROJECT_ROOT/$file" "$REMOTE_REPO_DIR/"
done

for dir in "${REPO_DIRS[@]}"; do
  remote_copy "$PROJECT_ROOT/$dir" "$REMOTE_REPO_DIR/" true
done

remote_bash <<EOF
printf '%s\n' "$LOCAL_COMMIT" > "$REMOTE_REPO_DIR/.deploy-commit"
find "$REMOTE_REPO_DIR" -type d -exec chmod g+rws {} + 2>/dev/null || true
find "$REMOTE_REPO_DIR" -type f -exec chmod g+rw {} + 2>/dev/null || true
find "$REMOTE_REPO_DIR" \( -type d -name '__pycache__' -o -type d -name '.pytest_cache' -o -type d -name 'pytest-cache-files-*' -o -type d -name '._*' \) -prune -exec rm -rf {} + 2>/dev/null || true
find "$REMOTE_REPO_DIR" -type f \( -name '._*' -o -name '.DS_Store' -o -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
sudo systemctl restart tinki-bot
sleep 3
sudo systemctl status tinki-bot --no-pager
EOF
