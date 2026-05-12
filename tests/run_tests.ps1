#!/usr/bin/env powershell
<#
.SYNOPSIS
    FasalX – Restart both microservices + Run all tests with structured logging.

USAGE (from repo root):
    .\tests\run_tests.ps1                          # run all tests
    .\tests\run_tests.ps1 -Suite backend           # backend tests only
    .\tests\run_tests.ps1 -Suite timeline          # timeline tests only
    .\tests\run_tests.ps1 -Coverage               # add HTML coverage report
    .\tests\run_tests.ps1 -SkipServerRestart       # skip kill/restart step
#>

param(
    [ValidateSet("all", "backend", "timeline")]
    [string]$Suite = "all",
    [switch]$Coverage,
    [switch]$SkipServerRestart
)

# ── Configuration ─────────────────────────────────────────────────────────────
$RepoRoot        = Split-Path -Parent $PSScriptRoot
$BackendDir      = Join-Path $RepoRoot "backend"
$TimelineDir     = Join-Path $RepoRoot "timeline_service"
$VenvPython      = Join-Path $RepoRoot "venv\Scripts\python.exe"
$LogsDir         = Join-Path $RepoRoot "tests\logs"
$Timestamp       = Get-Date -Format "yyyyMMdd_HHmmss"
$TestLogFile     = Join-Path $LogsDir "test_run_$Timestamp.log"

# ── Create logs directory ─────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

function Write-Header {
    param([string]$msg)
    $line = "=" * 70
    $out  = "`n$line`n  $msg`n$line"
    Write-Host $out -ForegroundColor Cyan
    Add-Content -Path $TestLogFile -Value $out
}

function Write-Step {
    param([string]$msg)
    $out = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $out -ForegroundColor Yellow
    Add-Content -Path $TestLogFile -Value $out
}

function Write-OK   { param([string]$m) Write-Host "  OK  $m" -ForegroundColor Green;  Add-Content $TestLogFile "  OK  $m" }
function Write-FAIL { param([string]$m) Write-Host "  FAIL $m" -ForegroundColor Red;    Add-Content $TestLogFile "  FAIL $m" }

# ─────────────────────────────────────────────────────────────────────────────
# 1. KILL EXISTING SERVERS
# ─────────────────────────────────────────────────────────────────────────────
if (-not $SkipServerRestart) {
    Write-Header "STEP 1 – Stopping existing uvicorn processes"

    $killed = Get-Process -Name "python" -ErrorAction SilentlyContinue |
              Where-Object { $_.MainWindowTitle -match "uvicorn" -or $_.CommandLine -match "uvicorn" }
    if ($killed) {
        $killed | Stop-Process -Force
        Write-OK "Killed $($killed.Count) uvicorn process(es)"
    } else {
        Write-Step "No running uvicorn processes found"
    }
    Start-Sleep -Seconds 1
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. START BACKEND (port 8000)
# ─────────────────────────────────────────────────────────────────────────────
if (-not $SkipServerRestart) {
    Write-Header "STEP 2 – Starting Backend on :8000"
    $BackendLog = Join-Path $LogsDir "backend_$Timestamp.log"

    $backendJob = Start-Process -FilePath $VenvPython `
        -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" `
        -WorkingDirectory $BackendDir `
        -RedirectStandardOutput $BackendLog `
        -RedirectStandardError  $BackendLog `
        -PassThru -WindowStyle Hidden

    Write-OK "Backend PID $($backendJob.Id)  |  log → $BackendLog"
    Start-Sleep -Seconds 3

    # Health-check
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
        if ($r.status -eq "healthy") { Write-OK "Backend health check passed" }
        else { Write-FAIL "Backend health check returned: $($r.status)" }
    } catch {
        Write-FAIL "Backend health check failed: $_"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. START TIMELINE SERVICE (port 8001)
# ─────────────────────────────────────────────────────────────────────────────
if (-not $SkipServerRestart) {
    Write-Header "STEP 3 – Starting Timeline Service on :8001"
    $TimelineLog = Join-Path $LogsDir "timeline_$Timestamp.log"

    $timelineJob = Start-Process -FilePath $VenvPython `
        -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload" `
        -WorkingDirectory $TimelineDir `
        -RedirectStandardOutput $TimelineLog `
        -RedirectStandardError  $TimelineLog `
        -PassThru -WindowStyle Hidden

    Write-OK "Timeline PID $($timelineJob.Id)  |  log → $TimelineLog"
    Start-Sleep -Seconds 3

    try {
        $r = Invoke-RestMethod -Uri "http://localhost:8001/health" -TimeoutSec 5
        if ($r.status -eq "healthy") { Write-OK "Timeline service health check passed" }
        else { Write-FAIL "Timeline health check returned: $($r.status)" }
    } catch {
        Write-FAIL "Timeline service health check failed (may be a .env / DB issue): $_"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. INSTALL TEST DEPENDENCIES (idempotent)
# ─────────────────────────────────────────────────────────────────────────────
Write-Header "STEP 4 – Installing test dependencies"
& $VenvPython -m pip install -q -r (Join-Path $PSScriptRoot "requirements-test.txt")
Write-OK "Dependencies up to date"

# ─────────────────────────────────────────────────────────────────────────────
# 5. SELECT TEST PATHS
# ─────────────────────────────────────────────────────────────────────────────
$TestPath = switch ($Suite) {
    "backend"  { "tests/backend" }
    "timeline" { "tests/timeline_service" }
    default    { "tests" }
}

# ─────────────────────────────────────────────────────────────────────────────
# 6. RUN PYTEST
# ─────────────────────────────────────────────────────────────────────────────
Write-Header "STEP 5 – Running pytest [$Suite suite]"

$PytestArgs = @(
    "-m", "pytest",
    $TestPath,
    "--tb=short",
    "-v",
    "--log-cli=true",
    "--log-cli-level=INFO",
    "--log-file=$TestLogFile",
    "--log-file-level=DEBUG"
)

if ($Coverage) {
    $PytestArgs += @(
        "--cov=backend/app",
        "--cov=timeline_service/app",
        "--cov-report=html:tests/logs/coverage_$Timestamp",
        "--cov-report=term-missing"
    )
}

Push-Location $RepoRoot
& $VenvPython @PytestArgs
$ExitCode = $LASTEXITCODE
Pop-Location

# ─────────────────────────────────────────────────────────────────────────────
# 7. SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
Write-Header "RESULT"
if ($ExitCode -eq 0) {
    Write-OK "All tests PASSED"
} else {
    Write-FAIL "Some tests FAILED (exit code $ExitCode)"
}

Write-Host "`n  Full log saved to: $TestLogFile" -ForegroundColor DarkCyan
if ($Coverage) {
    Write-Host "  Coverage HTML:      tests/logs/coverage_$Timestamp/index.html" -ForegroundColor DarkCyan
}

exit $ExitCode
