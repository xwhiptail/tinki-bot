param(
    [string]$Host = "52.91.60.81",
    [string]$User = "ec2-user",
    [string]$KeyPath = "I:\mybotserver.ppk",
    [string]$RemoteRepoDir = "/opt/apps/tinki-bot/repo",
    [string]$RemoteDataDir = "/opt/apps/tinki-bot/data"
)

$ErrorActionPreference = "Stop"

$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp = "C:\Program Files\PuTTY\pscp.exe"
$projectRoot = $PSScriptRoot

$repoFiles = @(
    "tinki-bot.py",
    "README.md",
    "requirements.txt",
    ".env.example",
    ".gitignore"
)

& $plink -batch -i $KeyPath "${User}@${Host}" @"
set -e
ts=`$(date +%Y%m%d_%H%M%S)
if [ -f ${RemoteRepoDir}/tinki-bot.py ]; then
  cp ${RemoteRepoDir}/tinki-bot.py ${RemoteRepoDir}/tinki-bot.py.backup_`$ts
fi
if [ -d ${RemoteDataDir} ]; then
  tar -czf /opt/apps/tinki-bot/data_backup_`$ts.tar.gz -C /opt/apps/tinki-bot data
fi
"@

foreach ($file in $repoFiles) {
    $localPath = Join-Path $projectRoot $file
    & $pscp -batch -i $KeyPath $localPath "${User}@${Host}:${RemoteRepoDir}/"
}

& $plink -batch -i $KeyPath "${User}@${Host}" "sudo systemctl restart tinki-bot && sleep 3 && sudo systemctl status tinki-bot --no-pager"
