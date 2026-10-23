[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'AnviRoute'),
    [string]$Python = 'python',
    [switch]$SkipPathUpdate
)

$ErrorActionPreference = 'Stop'
try {
    $projectSource = $PSScriptRoot
    $resolvedRoot = [IO.Path]::GetFullPath($InstallRoot)
    $runtimeDir = Join-Path $resolvedRoot 'runtime'
    $binDir = Join-Path $resolvedRoot 'bin'
    Write-Host "`nInstalling AnviRoute for your Windows account..." -ForegroundColor Cyan
    & $Python -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10 or newer is required"'
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.10+ from https://www.python.org/downloads/windows/ and enable Add Python to PATH.' }
    New-Item -ItemType Directory -Path $resolvedRoot, $binDir -Force | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $runtimeDir 'Scripts\python.exe'))) {
        & $Python -m venv $runtimeDir
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the private Python environment.' }
    }
    $runtimePython = Join-Path $runtimeDir 'Scripts\python.exe'
    $releaseWheel = Get-ChildItem -LiteralPath (Join-Path $projectSource 'dist') -Filter 'anviroute-*.whl' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($releaseWheel) {
        $installTarget = $releaseWheel.FullName
    } else {
        $installTarget = $projectSource
    }
    & $runtimePython -m pip install --disable-pip-version-check --no-deps --upgrade --force-reinstall $installTarget
    if ($LASTEXITCODE -ne 0) { throw 'Package installation failed. Check internet access and Python installation.' }
    $launcher = "@echo off`r`n`"$runtimePython`" -m anviroute %*`r`n"
    [IO.File]::WriteAllText((Join-Path $binDir 'anviroute.cmd'), $launcher, [Text.Encoding]::Default)
    if (-not $SkipPathUpdate) {
        $userPathValue = [Environment]::GetEnvironmentVariable('Path', 'User')
        $entries = @($userPathValue -split ';' | Where-Object { $_ })
        $alreadyPresent = @($entries | Where-Object { $_.TrimEnd('\') -ieq $binDir.TrimEnd('\') }).Count -gt 0
        if (-not $alreadyPresent) {
            [Environment]::SetEnvironmentVariable('Path', (($entries + $binDir) -join ';'), 'User')
        }
    }
    & $runtimePython -m anviroute --version
    if ($LASTEXITCODE -ne 0) { throw 'Installed package verification failed.' }
    Write-Host "`nAnviRoute installed successfully." -ForegroundColor Green
    Write-Host "Command folder: $binDir"
    if (-not $SkipPathUpdate) {
        Write-Host 'Close and reopen your terminal (restart VS Code if using its terminal).'
        Write-Host 'Then, from ANY project folder, run: anviroute.cmd run claude'
    }
    Write-Host 'Claude Code must already be installed and available on PATH.'
    exit 0
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
