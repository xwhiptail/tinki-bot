$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "remote-common.ps1")

$config = Get-RemoteCommandConfig -ProjectRoot $projectRoot

$result = Invoke-RemoteBash -Config $config -CaptureOutput -Script @'
set -e
printf '[repo-root]\n'
sudo find /opt/apps/tinki-bot -maxdepth 1 -mindepth 1 -printf '%TY-%Tm-%Td %TT %p\n' | sort

printf '\n[repo-garbage]\n'
sudo find /opt/apps/tinki-bot/repo -maxdepth 2 \( -name 'github-export-*' -o -name '*.backup_*' -o -name 'pytest-cache-files-*' -o -name '__pycache__' -o -name '.pytest_cache' \) -print | sort

printf '\n[tmp]\n'
sudo find /tmp -maxdepth 2 \( -name '*mojibake*' -o -name 'pytest-cache-files-*' -o -name 'tmp*pytest*' \) -print 2>/dev/null | sort
'@

$result | ForEach-Object { $_ }
