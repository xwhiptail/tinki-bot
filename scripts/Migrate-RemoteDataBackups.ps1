$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "remote-common.ps1")

$config = Get-RemoteCommandConfig -ProjectRoot $projectRoot

$result = Invoke-RemoteBash -Config $config -CaptureOutput -Script @'
set -e

backup_dir=/opt/apps/tinki-bot/backup
sudo mkdir -p "$backup_dir"

find /opt/apps/tinki-bot -maxdepth 1 -type f -name 'data_backup_*.tar.gz' -print0 | while IFS= read -r -d '' file; do
  sudo mv "$file" "$backup_dir"/
done

ls -1t "$backup_dir"/data_backup_*.tar.gz 2>/dev/null | tail -n +4 | xargs -r sudo rm --

printf '[backup-dir]\n'
sudo find "$backup_dir" -maxdepth 1 -type f -name 'data_backup_*.tar.gz' -printf '%TY-%Tm-%Td %TT %f\n' | sort
'@

$result | ForEach-Object { $_ }
