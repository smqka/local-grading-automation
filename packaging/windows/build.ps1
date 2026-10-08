<#
  Windows 10/11 x64 packaging script for local-grading-automation.
  Run from anywhere: powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1
  Build MACHINE needs Python + PyInstaller + Node.js + Inno Setup.
  Installer END USERS need none of these.
#>
[CmdletBinding()]
param([switch]$SkipInstaller)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Stage = Join-Path $RepoRoot 'dist\windows-stage'
$Work = Join-Path $RepoRoot 'build\pyinstaller'
$SourceEntry = Join-Path $PSScriptRoot 'api_entry.py'
$LauncherEntry = Join-Path $PSScriptRoot 'launcher.py'

if ($env:OS -ne 'Windows_NT') {
    throw 'This installer can only be built on Windows (use the included GitHub Actions workflow).'
}
Push-Location $RepoRoot
try {
    python --version
    node --version
    python -m PyInstaller --version
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller is not installed. Run: python -m pip install pyinstaller' }

    if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Stage, $Work | Out-Null
    $Bin = Join-Path $Stage 'bin'
    New-Item -ItemType Directory -Force -Path $Bin | Out-Null

    $common = @('--noconfirm', '--clean', '--onedir', '--distpath', $Bin, '--specpath', $Work, '--paths', $RepoRoot)

    Write-Host 'Building frozen grading API...' -ForegroundColor Cyan
    & python -m PyInstaller @common --name grading-api --workpath (Join-Path $Work 'api-work') $SourceEntry
    if ($LASTEXITCODE -ne 0) { throw 'Failed to build grading API.' }

    Write-Host 'Building GUI launcher...' -ForegroundColor Cyan
    & python -m PyInstaller @common --name launcher --windowed --workpath (Join-Path $Work 'launcher-work') $LauncherEntry
    if ($LASTEXITCODE -ne 0) { throw 'Failed to build launcher.' }

    $NodeExe = (Get-Command node -ErrorAction Stop).Source
    if (-not $NodeExe.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Expected node.exe but found $NodeExe"
    }
    $NodeTarget = Join-Path $Bin 'node'
    New-Item -ItemType Directory -Force -Path $NodeTarget | Out-Null
    Copy-Item $NodeExe (Join-Path $NodeTarget 'node.exe') -Force

    $App = Join-Path $Stage 'app'
    New-Item -ItemType Directory -Force -Path $App | Out-Null
    Copy-Item (Join-Path $RepoRoot 'server') (Join-Path $App 'server') -Recurse -Force
    Copy-Item (Join-Path $RepoRoot 'web') (Join-Path $App 'web') -Recurse -Force
    Copy-Item (Join-Path $RepoRoot 'package.json') (Join-Path $App 'package.json') -Force
    Copy-Item (Join-Path $RepoRoot 'LICENSE') (Join-Path $Stage 'LICENSE.txt') -Force
    Copy-Item (Join-Path $PSScriptRoot 'README_WINDOWS.md') (Join-Path $Stage 'README_WINDOWS.md') -Force

    $required = @(
        (Join-Path $Bin 'grading-api\grading-api.exe'),
        (Join-Path $Bin 'launcher\launcher.exe'),
        (Join-Path $Bin 'node\node.exe'),
        (Join-Path $App 'server\index.js'),
        (Join-Path $App 'web\index.html')
    )
    foreach ($file in $required) {
        if (-not (Test-Path $file)) { throw "Missing build output: $file" }
    }
    Write-Host "Created zero-prerequisite application payload at: $Stage" -ForegroundColor Green

    if (-not $SkipInstaller) {
        $ISCC = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
        ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
        if (-not $ISCC) { throw 'Inno Setup 6 is required on the build machine (or use GitHub Actions).' }
        & $ISCC (Join-Path $PSScriptRoot 'LocalGradingAutomation.iss')
        if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
        Write-Host "Installer ready in: $(Join-Path $RepoRoot 'dist\installer')" -ForegroundColor Green
    }
}
finally {
    Pop-Location
}
