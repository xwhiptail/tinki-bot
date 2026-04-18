function Get-RemoteCommandConfig {
    param(
        [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    )

    $localConfigPath = Join-Path $ProjectRoot "deploy-ec2.local.ps1"
    $config = [ordered]@{
        ServerHost = $env:TINKI_EC2_HOST
        User = "ec2-user"
        KeyPath = $env:TINKI_EC2_KEY_PATH
        RemoteRepoDir = "/opt/apps/tinki-bot/repo"
        RemoteDataDir = "/opt/apps/tinki-bot/data"
        Plink = "C:\Program Files\PuTTY\plink.exe"
        Pscp = "C:\Program Files\PuTTY\pscp.exe"
        ProjectRoot = $ProjectRoot
    }

    if (Test-Path $localConfigPath) {
        . $localConfigPath
        if ($ServerHost) { $config.ServerHost = $ServerHost }
        if ($User) { $config.User = $User }
        if ($KeyPath) { $config.KeyPath = $KeyPath }
        if ($RemoteRepoDir) { $config.RemoteRepoDir = $RemoteRepoDir }
        if ($RemoteDataDir) { $config.RemoteDataDir = $RemoteDataDir }
    }

    if (-not $config.ServerHost) {
        throw "Set ServerHost in deploy-ec2.local.ps1 or set the TINKI_EC2_HOST environment variable."
    }

    if (-not $config.KeyPath) {
        throw "Set KeyPath in deploy-ec2.local.ps1 or set the TINKI_EC2_KEY_PATH environment variable."
    }

    return [pscustomobject]$config
}

function Invoke-RemoteBash {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Config,
        [Parameter(Mandatory = $true)]
        [string]$Script,
        [switch]$CaptureOutput
    )

    $normalized = $Script -replace "`r`n", "`n"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($normalized)
    $b64 = [Convert]::ToBase64String($bytes)
    $remote = "echo '$b64' | base64 -d | bash"

    if ($CaptureOutput) {
        return & $Config.Plink -batch -i $Config.KeyPath "$($Config.User)@$($Config.ServerHost)" $remote
    }

    & $Config.Plink -batch -i $Config.KeyPath "$($Config.User)@$($Config.ServerHost)" $remote
    if ($LASTEXITCODE -ne 0) {
        throw "Remote bash command failed with exit code $LASTEXITCODE."
    }
}

function Copy-ToRemote {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Config,
        [Parameter(Mandatory = $true)]
        [string]$LocalPath,
        [Parameter(Mandatory = $true)]
        [string]$RemotePath,
        [switch]$Recursive
    )

    $leafName = Split-Path -Leaf $LocalPath
    $normalizedRemotePath = $RemotePath.TrimEnd("/")
    $remoteTarget = "$normalizedRemotePath/$leafName"

    Invoke-RemoteBash -Config $Config -Script @"
if [ "$($Recursive.IsPresent.ToString().ToLowerInvariant())" = "true" ]; then
  rm -rf $remoteTarget
else
  rm -f $remoteTarget
fi
"@

    $args = @("-batch", "-i", $Config.KeyPath)
    if ($Recursive) {
        $args += "-r"
    }
    $args += $LocalPath
    $args += "$($Config.User)@$($Config.ServerHost):$RemotePath"

    & $Config.Pscp @args
    if ($LASTEXITCODE -ne 0) {
        throw "Copy to remote failed for '$LocalPath'."
    }
}
