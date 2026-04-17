param(
    [switch]$RestartService
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "remote-common.ps1")

$config = Get-RemoteCommandConfig
$repo = $config.RemoteRepoDir

$steps = @()
if ($RestartService) {
    $steps += "sudo systemctl restart tinki-bot"
    $steps += "sleep 5"
}
$steps += "cd $repo"
$steps += "/opt/apps/tinki-bot/myenv/bin/python3.8 scripts/check_awscost.py"

Invoke-RemoteBash -Config $config -Script ($steps -join "`n")
