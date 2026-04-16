param(
    [string]$ServerHost = $env:TINKI_EC2_HOST,
    [string]$User = "ec2-user",
    [string]$KeyPath = "I:\mybotserver.ppk",
    [string]$RemoteRepoDir = "/opt/apps/tinki-bot/repo",
    [string]$RemoteDataDir = "/opt/apps/tinki-bot/data"
)

$ErrorActionPreference = "Stop"

$plink = "C:\Program Files\PuTTY\plink.exe"
$pscp = "C:\Program Files\PuTTY\pscp.exe"
$projectRoot = $PSScriptRoot
$localConfigPath = Join-Path $projectRoot "deploy-ec2.local.ps1"

if (Test-Path $localConfigPath) {
    . $localConfigPath
}

if (-not $ServerHost) {
    throw "Set ServerHost in deploy-ec2.local.ps1 or set the TINKI_EC2_HOST environment variable."
}

$repoFiles = @(
    "tinki-bot.py",
    "config.py",
    "README.md",
    "requirements.txt",
    ".env.example",
    ".gitignore"
)

$repoDirs = @("utils", "cogs")

$backupScript = @"
set -e
ts=`$(date +%Y%m%d_%H%M%S)
if [ -f ${RemoteRepoDir}/tinki-bot.py ]; then
  cp ${RemoteRepoDir}/tinki-bot.py ${RemoteRepoDir}/tinki-bot.py.backup_`$ts
fi
if [ -d ${RemoteDataDir} ]; then
  tar -czf /opt/apps/tinki-bot/data_backup_`$ts.tar.gz -C /opt/apps/tinki-bot data
fi
ls -1t ${RemoteRepoDir}/tinki-bot.py.backup_* 2>/dev/null | tail -n +4 | xargs -r rm --
ls -1t /opt/apps/tinki-bot/data_backup_*.tar.gz 2>/dev/null | tail -n +4 | xargs -r rm --
"@
$b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes(($backupScript -replace "`r`n", "`n")))
& $plink -batch -i $KeyPath "${User}@${ServerHost}" "echo '$b64' | base64 -d | bash"

# Create remote subdirectories
$mkdirScript = "mkdir -p " + ($repoDirs | ForEach-Object { "${RemoteRepoDir}/$_" }) -join " "
& $plink -batch -i $KeyPath "${User}@${ServerHost}" $mkdirScript

foreach ($file in $repoFiles) {
    $localPath = Join-Path $projectRoot $file
    & $pscp -batch -i $KeyPath $localPath "${User}@${ServerHost}:${RemoteRepoDir}/"
}

foreach ($dir in $repoDirs) {
    $localDir = Join-Path $projectRoot $dir
    & $pscp -batch -i $KeyPath -r $localDir "${User}@${ServerHost}:${RemoteRepoDir}/"
}

& $plink -batch -i $KeyPath "${User}@${ServerHost}" "sudo systemctl restart tinki-bot && sleep 3 && sudo systemctl status tinki-bot --no-pager"
