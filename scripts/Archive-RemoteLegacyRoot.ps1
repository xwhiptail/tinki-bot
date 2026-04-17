$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "remote-common.ps1")

$config = Get-RemoteCommandConfig -ProjectRoot $projectRoot

$result = Invoke-RemoteBash -Config $config -CaptureOutput -Script @'
set -e

archive_root="/opt/apps/tinki-bot/archive"
stamp="$(date +%Y%m%d_%H%M%S)"
target="$archive_root/root_legacy_$stamp"

sudo mkdir -p "$target"

for path in \
  /opt/apps/tinki-bot/altertable.py \
  /opt/apps/tinki-bot/commands \
  /opt/apps/tinki-bot/debug_animation.apng \
  /opt/apps/tinki-bot/glasses.png \
  /opt/apps/tinki-bot/memory_helper.py \
  /opt/apps/tinki-bot/requirements.txt \
  /opt/apps/tinki-bot/tinki-bot.py \
  /opt/apps/tinki-bot/tinki-bot.py_20250428_fail \
  /opt/apps/tinki-bot/twitter.py_backup_20231215 \
  /opt/apps/tinki-bot/twitter.py.bak \
  /opt/apps/tinki-bot/twitter.py.bak.bak \
  /opt/apps/tinki-bot/__pycache__ \
  /opt/apps/tinki-bot/.tinki-bot.py.swp
do
  if [ -e "$path" ]; then
    sudo mv "$path" "$target/"
  fi
done

find /opt/apps/tinki-bot -maxdepth 1 -type f \( -name '*.bak' -o -name '*backup*' \) -print0 | while IFS= read -r -d '' file; do
  case "$file" in
    /opt/apps/tinki-bot/data_backup_*.tar.gz)
      continue
      ;;
  esac
  sudo mv "$file" "$target/"
done

printf 'archived_to=%s\n' "$target"
printf '\n[archived]\n'
sudo find "$target" -maxdepth 1 -mindepth 1 -printf '%f\n' | sort
'@

$result | ForEach-Object { $_ }
