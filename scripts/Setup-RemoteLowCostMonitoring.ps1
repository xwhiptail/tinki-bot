param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "remote-common.ps1")

$config = Get-RemoteCommandConfig
$repo = $config.RemoteRepoDir

$quotedArgs = @()
foreach ($arg in $ScriptArgs) {
    $quotedArgs += "'" + ($arg -replace "'", "'\"'\"'") + "'"
}

$steps = @(
    "cd $repo",
    "/opt/apps/tinki-bot/myenv/bin/python scripts/setup_low_cost_monitoring.py $($quotedArgs -join ' ')"
)

Invoke-RemoteBash -Config $config -Script ($steps -join "`n")
