<# Smoke-test the *frozen* API and bundled node.exe on a Windows build worker. #>
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Stage = Join-Path $RepoRoot 'dist\windows-stage'
$apiExe = Join-Path $Stage 'bin\grading-api\grading-api.exe'
$nodeExe = Join-Path $Stage 'bin\node\node.exe'
$webScript = Join-Path $Stage 'app\server\index.js'
$apiProc = $null
$webProc = $null
$env:OPENAI_API_KEY = 'invalid-smoke-test-key-do-not-use'
$env:OPENAI_BASE_URL = 'https://api.openai.com/v1'
$env:OPENAI_MODEL = 'gpt-4.1'
$env:GRADING_API_HOST = '127.0.0.1'
$env:GRADING_API_PORT = '8765'
$env:GRADING_API_URL = 'http://127.0.0.1:8765'
$env:GRADING_API_TOKEN = 'one-time-build-smoke-token'
$env:PORT = '5175'
try {
    $apiProc = Start-Process -FilePath $apiExe -WorkingDirectory (Join-Path $Stage 'app') -PassThru -NoNewWindow
    $webProc = Start-Process -FilePath $nodeExe -ArgumentList @($webScript) -WorkingDirectory (Join-Path $Stage 'app') -PassThru -NoNewWindow
    $verified = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if ($apiProc.HasExited -or $webProc.HasExited) { throw 'A frozen background service exited unexpectedly.' }
        try {
            $a = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 2
            $w = Invoke-RestMethod -Uri 'http://127.0.0.1:5175/api/health' -TimeoutSec 2
            if ($a.status -eq 'ok' -and $w.service -eq 'exam-grading-assistant' -and $w.gradingApi.ok) {
                $verified = $true
                break
            }
        }
        catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $verified) { throw 'Frozen servers did not pass the HTTP health checks.' }
    $html = Invoke-WebRequest -Uri 'http://127.0.0.1:5175/' -TimeoutSec 5
    if ($html.StatusCode -ne 200) { throw 'The bundled web frontend is not accessible.' }
    Write-Host 'PASS: frozen Python API, bundled Node web service, and web frontend.' -ForegroundColor Green
}
finally {
    foreach ($p in @($webProc, $apiProc)) {
        if ($null -ne $p -and -not $p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
