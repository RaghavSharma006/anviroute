[CmdletBinding()]
param(
    [string]$InstallRoot = $(if ($env:ANVIROUTE_INSTALL_ROOT) { $env:ANVIROUTE_INSTALL_ROOT } else { Join-Path $env:USERPROFILE '.anviroute' }),
    [string]$Python = 'python',
    [string]$PayloadBase64 = '',
    [string]$PayloadHash = '',
    [switch]$SkipPathUpdate = ($env:ANVIROUTE_SKIP_PATH_UPDATE -eq '1')
)

$ErrorActionPreference = 'Stop'
try {
    $resolvedRoot = [IO.Path]::GetFullPath($InstallRoot)
    $binDir = Join-Path $resolvedRoot 'bin'
    $appPath = Join-Path $resolvedRoot 'anviroute.pyz'
    $pythonExecutable = $null
    foreach ($candidate in (@($Python, 'py', 'python3') | Select-Object -Unique)) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        $probeArgs = @('-c', 'import sys; assert sys.version_info >= (3, 10); print(sys.executable)')
        if ($candidate -eq 'py') { $probeArgs = @('-3') + $probeArgs }
        $probe = & $command.Source @probeArgs 2>$null
        if ($LASTEXITCODE -eq 0 -and $probe -and (Test-Path -LiteralPath ($probe | Select-Object -Last 1))) {
            $pythonExecutable = ($probe | Select-Object -Last 1).Trim()
            break
        }
    }
    if (-not $pythonExecutable) { throw 'Python 3.10+ is required. Install it from python.org with Add Python to PATH enabled.' }
    New-Item -ItemType Directory -Path $resolvedRoot, $binDir -Force | Out-Null
    if ($PayloadBase64) {
        $payloadBytes = [Convert]::FromBase64String($PayloadBase64)
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { $actualHash = ([BitConverter]::ToString($hasher.ComputeHash($payloadBytes))).Replace('-', '').ToLowerInvariant() } finally { $hasher.Dispose() }
        if (-not $PayloadHash -or $actualHash -ne $PayloadHash) { throw 'AnviRoute download is damaged; download it again.' }
        [IO.File]::WriteAllBytes($appPath, $payloadBytes)
    } else {
        $archivePath = Join-Path $PSScriptRoot 'dist\anviroute.pyz'
        if (-not (Test-Path -LiteralPath $archivePath)) {
            & $pythonExecutable (Join-Path $PSScriptRoot 'scripts\build_release.py')
            if ($LASTEXITCODE -ne 0) { throw 'Could not package the local source.' }
        }
        Copy-Item -LiteralPath $archivePath -Destination $appPath -Force
    }
    & $pythonExecutable $appPath --version
    if ($LASTEXITCODE -ne 0) { throw 'AnviRoute verification failed.' }
    $launcher = "@echo off`r`n`"$pythonExecutable`" -B `"$appPath`" %*`r`n"
    [IO.File]::WriteAllText((Join-Path $binDir 'anviroute.cmd'), $launcher, [Text.Encoding]::Default)
    if (-not $SkipPathUpdate) {
        $userPathValue = [Environment]::GetEnvironmentVariable('Path', 'User')
        $entries = @($userPathValue -split ';' | Where-Object { $_ })
        $entries = @($entries | Where-Object { $_.TrimEnd('\') -ine $binDir.TrimEnd('\') })
        [Environment]::SetEnvironmentVariable('Path', ((@($binDir) + $entries) -join ';'), 'User')
    }
    Write-Host 'AnviRoute ready. No pip, dependencies, or private Python environment needed.' -ForegroundColor Green
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
