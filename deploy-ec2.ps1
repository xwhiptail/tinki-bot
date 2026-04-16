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
$remoteName = "origin"

if (Test-Path $localConfigPath) {
    . $localConfigPath
}

if (-not $ServerHost) {
    throw "Set ServerHost in deploy-ec2.local.ps1 or set the TINKI_EC2_HOST environment variable."
}

$localCommit = (& git -C $projectRoot rev-parse HEAD).Trim()
if (-not $localCommit) {
    throw "Unable to determine local git commit."
}

$remoteUrl = (& git -C $projectRoot remote get-url $remoteName).Trim()
if (-not $remoteUrl) {
    throw "Unable to determine git remote URL for '$remoteName'."
}

$lsRemote = (& git -C $projectRoot ls-remote $remoteUrl refs/heads/main).Trim()
if (-not $lsRemote) {
    throw "Unable to determine GitHub main commit from '$remoteUrl'."
}
$githubCommit = ($lsRemote -split "\s+")[0]
if (-not $githubCommit) {
    throw "Unable to parse GitHub main commit."
}

Write-Host ("Local HEAD:    {0}" -f $localCommit.Substring(0, 7))
Write-Host ("GitHub main:   {0}" -f $githubCommit.Substring(0, 7))

if ($localCommit -ne $githubCommit) {
    throw "Local HEAD does not match GitHub main. Pull/push first so deploy matches GitHub."
}

$repoFiles = @(
    "tinki-bot.py",
    "config.py",
    "README.md",
    "INSTALL.md",
    "CLAUDE.md",
    "AGENTS.md",
    "requirements.txt",
    "pytest.ini",
    ".env.example",
    ".gitignore"
)

$repoDirs = @("utils", "cogs", "tests", "assets")

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

$deployedCommitRaw = & $plink -batch -i $KeyPath "${User}@${ServerHost}" "cat ${RemoteRepoDir}/.deploy-commit 2>/dev/null || true"
$deployedCommit = ""
if ($null -ne $deployedCommitRaw) {
    $deployedCommit = [string]::Concat($deployedCommitRaw).Trim()
}
if ($deployedCommit) {
    Write-Host ("Deployed now:  {0}" -f $deployedCommit.Substring(0, [Math]::Min(7, $deployedCommit.Length)))
} else {
    Write-Host "Deployed now:  unknown"
}

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

& $plink -batch -i $KeyPath "${User}@${ServerHost}" "printf '%s`n' '$localCommit' > ${RemoteRepoDir}/.deploy-commit"
& $plink -batch -i $KeyPath "${User}@${ServerHost}" "sudo systemctl restart tinki-bot && sleep 3 && sudo systemctl status tinki-bot --no-pager"
