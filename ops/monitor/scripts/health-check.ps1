# ============================================================================
# 监控系统健康巡检脚本
# 
# 用法: .\health-check.ps1 [-Verbose]
# 
# 功能:
#   - 检查 Aggregator 服务状态
#   - 检查 API 可用性
#   - 检查数据库状态
#   - 测试 Agent 连通性
# ============================================================================

param(
    [switch]$Verbose
)

# 配置
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MonitorDir = Split-Path -Parent $ScriptDir
$DataDir = Join-Path $MonitorDir "data"
$DbFile = Join-Path $DataDir "monitor.db"
$ConfigFile = Join-Path $MonitorDir "config.yaml"

# 默认配置（从 config.yaml 读取或使用默认值）
$ApiHost = "localhost"
$ApiPort = 8080
$ApiBaseUrl = "http://${ApiHost}:${ApiPort}"

# 统计
$checksPassed = 0
$checksFailed = 0
$checksWarning = 0

function Write-CheckResult {
    param(
        [string]$Name,
        [string]$Status,  # pass, fail, warn
        [string]$Message
    )
    
    $icon = switch ($Status) {
        "pass" { "✅"; $script:checksPassed++ }
        "fail" { "❌"; $script:checksFailed++ }
        "warn" { "⚠️"; $script:checksWarning++ }
    }
    
    $color = switch ($Status) {
        "pass" { "Green" }
        "fail" { "Red" }
        "warn" { "Yellow" }
    }
    
    Write-Host "$icon $Name" -ForegroundColor $color
    if ($Message -and $Verbose) {
        Write-Host "   $Message" -ForegroundColor Gray
    }
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  监控系统健康巡检" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

# ----------------------------------------------------------------------------
# 1. 检查 Aggregator 服务
# ----------------------------------------------------------------------------
Write-Host "[1/5] Aggregator 服务状态" -ForegroundColor Yellow

# 检查 NSSM 服务
$serviceName = "MonitorAggregator"
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue

if ($service) {
    if ($service.Status -eq "Running") {
        Write-CheckResult -Name "NSSM 服务" -Status "pass" -Message "服务运行中"
    } else {
        Write-CheckResult -Name "NSSM 服务" -Status "fail" -Message "服务状态: $($service.Status)"
    }
} else {
    # 可能是 Python 进程直接运行
    $pythonProc = Get-Process -Name "python*" -ErrorAction SilentlyContinue | 
        Where-Object { $_.CommandLine -match "monitor_aggregator" }
    
    if ($pythonProc) {
        Write-CheckResult -Name "Aggregator 进程" -Status "pass" -Message "进程运行中 (PID: $($pythonProc.Id))"
    } else {
        Write-CheckResult -Name "Aggregator 服务" -Status "warn" -Message "未找到 NSSM 服务或 Python 进程"
    }
}

Write-Host ""

# ----------------------------------------------------------------------------
# 2. 检查 API 可用性
# ----------------------------------------------------------------------------
Write-Host "[2/5] API 可用性" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "$ApiBaseUrl/api/servers" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    
    if ($response.StatusCode -eq 200) {
        $servers = $response.Content | ConvertFrom-Json
        Write-CheckResult -Name "API 端点 /api/servers" -Status "pass" -Message "响应正常，服务器数量: $($servers.Count)"
    } else {
        Write-CheckResult -Name "API 端点 /api/servers" -Status "fail" -Message "状态码: $($response.StatusCode)"
    }
} catch {
    Write-CheckResult -Name "API 端点 /api/servers" -Status "fail" -Message "无法连接: $($_.Exception.Message)"
}

try {
    $response = Invoke-WebRequest -Uri "$ApiBaseUrl/api/events?limit=1" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    
    if ($response.StatusCode -eq 200) {
        Write-CheckResult -Name "API 端点 /api/events" -Status "pass" -Message "响应正常"
    } else {
        Write-CheckResult -Name "API 端点 /api/events" -Status "fail" -Message "状态码: $($response.StatusCode)"
    }
} catch {
    Write-CheckResult -Name "API 端点 /api/events" -Status "fail" -Message "无法连接: $($_.Exception.Message)"
}

Write-Host ""

# ----------------------------------------------------------------------------
# 3. 检查数据库
# ----------------------------------------------------------------------------
Write-Host "[3/5] 数据库状态" -ForegroundColor Yellow

if (Test-Path $DbFile) {
    $dbInfo = Get-Item $DbFile
    $sizeMB = [math]::Round($dbInfo.Length / 1MB, 2)
    
    # 检查文件大小
    if ($sizeMB -lt 100) {
        Write-CheckResult -Name "数据库文件" -Status "pass" -Message "大小: $sizeMB MB"
    } elseif ($sizeMB -lt 500) {
        Write-CheckResult -Name "数据库文件" -Status "warn" -Message "大小: $sizeMB MB（建议关注）"
    } else {
        Write-CheckResult -Name "数据库文件" -Status "warn" -Message "大小: $sizeMB MB（建议清理或归档）"
    }
    
    # 检查 WAL 文件
    $walFile = "$DbFile-wal"
    if (Test-Path $walFile) {
        $walInfo = Get-Item $walFile
        $walSizeMB = [math]::Round($walInfo.Length / 1MB, 2)
        if ($walSizeMB -lt 10) {
            Write-CheckResult -Name "WAL 日志" -Status "pass" -Message "大小: $walSizeMB MB"
        } else {
            Write-CheckResult -Name "WAL 日志" -Status "warn" -Message "大小: $walSizeMB MB（建议执行 checkpoint）"
        }
    }
    
    # 检查数据库查询
    $sqlite3 = Get-Command "sqlite3.exe" -ErrorAction SilentlyContinue
    if ($sqlite3) {
        try {
            $serverCount = & sqlite3.exe $DbFile "SELECT COUNT(*) FROM servers;"
            $sampleCount = & sqlite3.exe $DbFile "SELECT COUNT(*) FROM samples_hourly;"
            $eventCount = & sqlite3.exe $DbFile "SELECT COUNT(*) FROM events;"
            
            Write-CheckResult -Name "数据统计" -Status "pass" -Message "服务器: $serverCount, 样本: $sampleCount, 事件: $eventCount"
        } catch {
            Write-CheckResult -Name "数据库查询" -Status "fail" -Message $_.Exception.Message
        }
    }
} else {
    Write-CheckResult -Name "数据库文件" -Status "fail" -Message "文件不存在: $DbFile"
}

Write-Host ""

# ----------------------------------------------------------------------------
# 4. 检查 Agent 连通性
# ----------------------------------------------------------------------------
Write-Host "[4/5] Agent 连通性" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "$ApiBaseUrl/api/servers" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    $servers = $response.Content | ConvertFrom-Json
    
    if ($servers.Count -eq 0) {
        Write-CheckResult -Name "Agent 列表" -Status "warn" -Message "未配置任何服务器"
    } else {
        $onlineCount = ($servers | Where-Object { $_.online -eq $true }).Count
        $offlineCount = $servers.Count - $onlineCount
        
        if ($offlineCount -eq 0) {
            Write-CheckResult -Name "Agent 状态" -Status "pass" -Message "全部在线 ($onlineCount/$($servers.Count))"
        } elseif ($onlineCount -gt 0) {
            Write-CheckResult -Name "Agent 状态" -Status "warn" -Message "部分离线 ($onlineCount/$($servers.Count) 在线)"
        } else {
            Write-CheckResult -Name "Agent 状态" -Status "fail" -Message "全部离线 (0/$($servers.Count) 在线)"
        }
        
        # 详细列出每台服务器状态
        if ($Verbose) {
            foreach ($server in $servers) {
                $status = if ($server.online) { "✅ 在线" } else { "❌ 离线" }
                Write-Host "   $status - $($server.name) ($($server.host):$($server.agent_port))" -ForegroundColor Gray
            }
        }
    }
} catch {
    Write-CheckResult -Name "Agent 状态检查" -Status "fail" -Message "无法获取服务器列表: $($_.Exception.Message)"
}

Write-Host ""

# ----------------------------------------------------------------------------
# 5. 检查磁盘空间
# ----------------------------------------------------------------------------
Write-Host "[5/5] 磁盘空间" -ForegroundColor Yellow

$drive = Split-Path $MonitorDir -Qualifier
$diskInfo = Get-PSDrive -Name $drive.TrimEnd(':')
$freeGB = [math]::Round($diskInfo.Free / 1GB, 2)
$usedPct = [math]::Round((1 - $diskInfo.Free / ($diskInfo.Used + $diskInfo.Free)) * 100, 1)

if ($usedPct -lt 80) {
    Write-CheckResult -Name "磁盘空间 ($drive)" -Status "pass" -Message "剩余: $freeGB GB (使用率: $usedPct%)"
} elseif ($usedPct -lt 90) {
    Write-CheckResult -Name "磁盘空间 ($drive)" -Status "warn" -Message "剩余: $freeGB GB (使用率: $usedPct%)"
} else {
    Write-CheckResult -Name "磁盘空间 ($drive)" -Status "fail" -Message "剩余: $freeGB GB (使用率: $usedPct%)"
}

Write-Host ""

# ----------------------------------------------------------------------------
# 汇总结果
# ----------------------------------------------------------------------------
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  巡检完成" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$totalChecks = $checksPassed + $checksFailed + $checksWarning
Write-Host "📊 检查结果汇总:"
Write-Host "   ✅ 通过: $checksPassed" -ForegroundColor Green
Write-Host "   ⚠️  警告: $checksWarning" -ForegroundColor Yellow
Write-Host "   ❌ 失败: $checksFailed" -ForegroundColor Red
Write-Host ""

if ($checksFailed -gt 0) {
    Write-Host "🔴 系统状态: 异常" -ForegroundColor Red
    exit 1
} elseif ($checksWarning -gt 0) {
    Write-Host "🟡 系统状态: 需关注" -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "🟢 系统状态: 正常" -ForegroundColor Green
    exit 0
}
