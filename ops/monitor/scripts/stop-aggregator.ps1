param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "Stopping Monitor Aggregator..." -ForegroundColor Yellow

# 1) Stop Windows service if installed
$serviceName = "MonitorAggregator"
$svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($svc) {
    if ($svc.Status -ne "Stopped") {
        Write-Host "Stopping service: $serviceName ($($svc.Status))" -ForegroundColor Yellow
        try {
            Stop-Service -Name $serviceName -Force:$Force -ErrorAction Stop
        } catch {
            Write-Host "Failed to stop service: $serviceName ($($_.Exception.Message))" -ForegroundColor Red
        }
        Start-Sleep -Seconds 1
    } else {
        Write-Host "Service already stopped: $serviceName ($($svc.Status))" -ForegroundColor Gray
    }
}

# 2) Stop stray python processes started manually
$procs = @(Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -in @("python.exe","pythonw.exe")) -and
    ($_.CommandLine -match "monitor_aggregator")
})

if ($procs.Count -eq 0) {
    Write-Host "No running monitor_aggregator processes found." -ForegroundColor Green
    exit 0
}

foreach ($p in $procs) {
    Write-Host "Stopping PID $($p.ProcessId): $($p.CommandLine)" -ForegroundColor Yellow
    try {
        Stop-Process -Id $p.ProcessId -Force:$Force -ErrorAction Stop
    } catch {
        Write-Host "Failed to stop PID $($p.ProcessId): $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host "Done." -ForegroundColor Green
