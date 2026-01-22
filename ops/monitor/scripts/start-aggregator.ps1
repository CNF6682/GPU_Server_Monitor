param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

$serviceName = "MonitorAggregator"

$svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($svc) {
    if ($Restart) {
        Write-Host "Restarting Windows service: $serviceName" -ForegroundColor Yellow
        Restart-Service -Name $serviceName -ErrorAction Stop
    } else {
        if ($svc.Status -eq "Paused") {
            Write-Host "Resuming Windows service: $serviceName" -ForegroundColor Yellow
            Resume-Service -Name $serviceName -ErrorAction Stop
        } elseif ($svc.Status -ne "Running") {
            Write-Host "Starting Windows service: $serviceName" -ForegroundColor Yellow
            Start-Service -Name $serviceName -ErrorAction Stop
        } else {
            Write-Host "Service already running: $serviceName" -ForegroundColor Green
        }
    }
    Write-Host "OK. Check: http://localhost:8080" -ForegroundColor Green
    exit 0
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MonitorDir = Split-Path -Parent $ScriptDir             # ops/monitor
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MonitorDir)  # repo root
$AggregatorDir = Join-Path $MonitorDir "aggregator"

$ConfigPath = Join-Path $MonitorDir "config.yaml"
$PythonVenv = Join-Path $AggregatorDir ".venv\\Scripts\\python.exe"

if ($Restart) {
    & (Join-Path $ScriptDir "stop-aggregator.ps1") -Force
}

if (-not (Test-Path $ConfigPath)) {
    throw "Config not found: $ConfigPath"
}

$env:MONITOR_CONFIG_PATH = $ConfigPath

$pythonExe = "python"
if (Test-Path $PythonVenv) {
    $internalName = (Get-Item $PythonVenv -ErrorAction SilentlyContinue).VersionInfo.InternalName

    # Some environments have venv's python.exe as py.exe (Python Launcher), which spawns an extra child process.
    # Prefer a real python.exe when possible.
    if ($internalName -and $internalName -ne "Python Launcher") {
        $pythonExe = $PythonVenv
    }
}

Write-Host "Starting Monitor Aggregator..." -ForegroundColor Yellow
Write-Host "  RepoRoot: $RepoRoot" -ForegroundColor Gray
Write-Host "  WorkDir : $AggregatorDir" -ForegroundColor Gray
Write-Host "  Python  : $pythonExe" -ForegroundColor Gray
Write-Host "  Config  : $env:MONITOR_CONFIG_PATH" -ForegroundColor Gray

Start-Process -FilePath $pythonExe -ArgumentList @("-m","monitor_aggregator.main") -WorkingDirectory $AggregatorDir

Write-Host "Started. Check: http://localhost:8080" -ForegroundColor Green
