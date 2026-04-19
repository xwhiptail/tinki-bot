$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "remote-common.ps1")

$config = Get-RemoteCommandConfig
$repo = $config.RemoteRepoDir

Invoke-RemoteBash -Config $config -Script @"
cd $repo
sudo bash scripts/install_host_metrics_timer.sh
"@
