$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "remote-common.ps1")

$config = Get-RemoteCommandConfig -ProjectRoot $projectRoot

$result = Invoke-RemoteBash -Config $config -CaptureOutput -Script @'
set -e

archive_root="/opt/apps/tinki-bot/archive"
stamp="$(date +%Y%m%d_%H%M%S)"
target="$archive_root/root_data_duplicates_$stamp"

sudo mkdir -p "$target"

for name in \
  conversations.json \
  distribution_graph.png \
  explode.json \
  explode_usage_graph.png \
  personas.json \
  reminders.db \
  scores.json \
  scores_graph.png \
  spinny.json \
  spinny_usage_graph.png \
  sus_and_sticker_usage.json \
  sussy_usage_distribution.png \
  sussy_usage_graph.png
do
  root_path="/opt/apps/tinki-bot/$name"
  data_path="/opt/apps/tinki-bot/data/$name"
  if [ -e "$root_path" ] && [ -e "$data_path" ]; then
    sudo mv "$root_path" "$target/"
  fi
done

for path in \
  /opt/apps/tinki-bot/conversation_logs.db \
  /opt/apps/tinki-bot/explode_usage_graph.png \
  /opt/apps/tinki-bot/scores_graph.png \
  /opt/apps/tinki-bot/spinny_usage_graph.png \
  /opt/apps/tinki-bot/sussy_usage_distribution.png \
  /opt/apps/tinki-bot/sussy_usage_graph.png
do
  if [ -e "$path" ]; then
    sudo mv "$path" "$target/"
  fi
done

printf 'archived_to=%s\n' "$target"
printf '\n[archived]\n'
sudo find "$target" -maxdepth 1 -mindepth 1 -printf '%f\n' | sort
'@

$result | ForEach-Object { $_ }
