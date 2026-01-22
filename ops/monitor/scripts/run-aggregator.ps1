param()

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MonitorDir = Split-Path -Parent $ScriptDir             # ops/monitor
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MonitorDir)  # repo root
$AggregatorDir = Join-Path $MonitorDir "aggregator"

$ConfigPath = Join-Path $MonitorDir "config.yaml"
$PythonVenv = Join-Path $AggregatorDir ".venv\\Scripts\\python.exe"

if (-not (Test-Path $ConfigPath)) {
    throw "Config not found: $ConfigPath"
}

$env:MONITOR_CONFIG_PATH = $ConfigPath
$env:PYTHONUNBUFFERED = "1"

function Get-VenvBasePythonFromPyVenvCfg([string]$venvDir) {
    $cfgPath = Join-Path $venvDir "pyvenv.cfg"
    if (-not (Test-Path $cfgPath)) { return $null }

    $raw = Get-Content -Path $cfgPath -ErrorAction SilentlyContinue
    foreach ($line in $raw) {
        if ($line -match '^\s*executable\s*=\s*(.+)\s*$') {
            $exe = $Matches[1].Trim()
            if ($exe -and (Test-Path $exe)) { return $exe }
        }
        if ($line -match '^\s*home\s*=\s*(.+)\s*$') {
            $homeDir = $Matches[1].Trim()
            $homePython = Join-Path $homeDir "python.exe"
            if ($homeDir -and (Test-Path $homePython)) { return $homePython }
        }
    }

    return $null
}

function Resolve-PythonExe([string]$pythonVenvPath, [string]$venvDir) {
    # Prefer venv python when present (even if it is a launcher stub), because it guarantees venv site-packages.
    if (Test-Path $pythonVenvPath) {
        return $pythonVenvPath
    }

    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) {
        return $cmd.Source
    }

    $baseFromCfg = Get-VenvBasePythonFromPyVenvCfg -venvDir $venvDir
    if ($baseFromCfg) {
        return $baseFromCfg
    }

    throw "Python executable not found. Install Python or ensure it is available to the Windows service account."
}

$venvDir = Join-Path $AggregatorDir ".venv"
$pythonExe = Resolve-PythonExe -pythonVenvPath $PythonVenv -venvDir $venvDir

Write-Host "Running Monitor Aggregator (service mode)..." -ForegroundColor Yellow
Write-Host "  RepoRoot: $RepoRoot" -ForegroundColor Gray
Write-Host "  WorkDir : $AggregatorDir" -ForegroundColor Gray
Write-Host "  Python  : $pythonExe" -ForegroundColor Gray
Write-Host "  Config  : $env:MONITOR_CONFIG_PATH" -ForegroundColor Gray

Push-Location $AggregatorDir
try {
    & $pythonExe -m monitor_aggregator.main
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
