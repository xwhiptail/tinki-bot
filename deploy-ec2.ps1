$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$remoteName = "origin"
. (Join-Path $projectRoot "scripts\remote-common.ps1")
$config = Get-RemoteCommandConfig -ProjectRoot $projectRoot

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
    "deploy-ec2.sh",
    "deploy-ec2.ps1",
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

$repoDirs = @("utils", "cogs", "tests", "scripts")

Invoke-RemoteBash -Config $config -Script @"
set -e
ts=`$(date +%Y%m%d_%H%M%S)
backup_dir=/opt/apps/tinki-bot/backup
mkdir -p "`$backup_dir"
if [ -f $($config.RemoteRepoDir)/tinki-bot.py ]; then
  cp $($config.RemoteRepoDir)/tinki-bot.py $($config.RemoteRepoDir)/tinki-bot.py.backup_`$ts
fi
if [ -d $($config.RemoteDataDir) ]; then
  tar -czf "`$backup_dir"/data_backup_`$ts.tar.gz -C /opt/apps/tinki-bot data
fi
ls -1t $($config.RemoteRepoDir)/tinki-bot.py.backup_* 2>/dev/null | tail -n +4 | xargs -r rm --
ls -1t "`$backup_dir"/data_backup_*.tar.gz 2>/dev/null | tail -n +4 | xargs -r rm --
"@

$deployedCommitRaw = Invoke-RemoteBash -Config $config -CaptureOutput -Script @"
if [ -f $($config.RemoteRepoDir)/.deploy-commit ]; then
  cat $($config.RemoteRepoDir)/.deploy-commit
fi
"@
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
Invoke-RemoteBash -Config $config -Script ("mkdir -p " + (($repoDirs | ForEach-Object { "$($config.RemoteRepoDir)/$_" }) -join " "))

foreach ($file in $repoFiles) {
    $localPath = Join-Path $projectRoot $file
    Copy-ToRemote -Config $config -LocalPath $localPath -RemotePath "$($config.RemoteRepoDir)/"
}

foreach ($dir in $repoDirs) {
    $localDir = Join-Path $projectRoot $dir
    Copy-ToRemote -Config $config -LocalPath $localDir -RemotePath "$($config.RemoteRepoDir)/" -Recursive
}

Invoke-RemoteBash -Config $config -Script @"
printf '%s\n' '$localCommit' > $($config.RemoteRepoDir)/.deploy-commit
find $($config.RemoteRepoDir) -type d -exec chmod g+rws {} + 2>/dev/null || true
find $($config.RemoteRepoDir) -type f -exec chmod g+rw {} + 2>/dev/null || true
find $($config.RemoteRepoDir) \( -type d -name '__pycache__' -o -type d -name '.pytest_cache' -o -type d -name 'pytest-cache-files-*' \) -prune -exec rm -rf {} +
find $($config.RemoteRepoDir) -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
sudo systemctl restart tinki-bot
sleep 3
sudo systemctl status tinki-bot --no-pager
"@
