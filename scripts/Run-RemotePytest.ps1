$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "remote-common.ps1")

$config = Get-RemoteCommandConfig
$repo = $config.RemoteRepoDir

Invoke-RemoteBash -Config $config -Script @"
cd $repo
/opt/apps/tinki-bot/myenv/bin/python3.8 -m pytest -q
"@
