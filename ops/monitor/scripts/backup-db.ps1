# ============================================================================
# 数据库备份脚本
# 
# 用法: .\backup-db.ps1 [-Retention <days>]
# 
# 参数:
#   -Retention    备份保留天数（默认 7 天）
# 
# 功能:
#   - 创建数据库快照备份
#   - 自动清理过期备份
# ============================================================================

param(
    [int]$Retention = 7
)

# 配置
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MonitorDir = Split-Path -Parent $ScriptDir
$DataDir = Join-Path $MonitorDir "data"
$BackupDir = Join-Path $MonitorDir "backup"
$DbFile = Join-Path $DataDir "monitor.db"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = Join-Path $BackupDir "monitor-$Timestamp.db"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  监控系统数据库备份" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

# ----------------------------------------------------------------------------
# Step 1: 检查数据库文件
# ----------------------------------------------------------------------------
Write-Host "[1/4] 检查数据库文件..." -ForegroundColor Yellow

if (-not (Test-Path $DbFile)) {
    Write-Host "❌ 错误: 数据库文件不存在: $DbFile" -ForegroundColor Red
    exit 1
}

$dbInfo = Get-Item $DbFile
Write-Host "✅ 数据库: $DbFile" -ForegroundColor Green
Write-Host "   大小: $([math]::Round($dbInfo.Length / 1KB, 2)) KB"

# ----------------------------------------------------------------------------
# Step 2: 创建备份目录
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/4] 准备备份目录..." -ForegroundColor Yellow

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    Write-Host "✅ 创建目录: $BackupDir" -ForegroundColor Green
} else {
    Write-Host "✅ 备份目录: $BackupDir" -ForegroundColor Green
}

# ----------------------------------------------------------------------------
# Step 3: 执行备份
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "[3/4] 执行备份..." -ForegroundColor Yellow

# 查找 SQLite3
$sqlite3Paths = @(
    "sqlite3.exe",
    "C:\Program Files\SQLite\sqlite3.exe",
    "C:\sqlite\sqlite3.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\sqlite3.exe")
)

$sqlite3 = $null
foreach ($path in $sqlite3Paths) {
    if (Get-Command $path -ErrorAction SilentlyContinue) {
        $sqlite3 = $path
        break
    }
}

if ($sqlite3) {
    # 使用 SQLite 在线备份（推荐，WAL 模式安全）
    try {
        $backupCmd = ".backup '$BackupFile'"
        echo $backupCmd | & $sqlite3 $DbFile
        
        if ($LASTEXITCODE -eq 0 -and (Test-Path $BackupFile)) {
            $backupInfo = Get-Item $BackupFile
            Write-Host "✅ 备份成功: $BackupFile" -ForegroundColor Green
            Write-Host "   大小: $([math]::Round($backupInfo.Length / 1KB, 2)) KB"
        } else {
            throw "SQLite 备份失败"
        }
    } catch {
        Write-Host "⚠️  SQLite 备份失败，尝试文件复制..." -ForegroundColor Yellow
        Copy-Item $DbFile $BackupFile -Force
        Write-Host "✅ 文件复制备份完成: $BackupFile" -ForegroundColor Green
    }
} else {
    # 直接文件复制（不推荐在 WAL 模式下使用）
    Write-Host "⚠️  未找到 SQLite3，使用文件复制备份..." -ForegroundColor Yellow
    Copy-Item $DbFile $BackupFile -Force
    
    # 同时复制 WAL 文件（如果存在）
    $walFile = "$DbFile-wal"
    $shmFile = "$DbFile-shm"
    if (Test-Path $walFile) {
        Copy-Item $walFile "$BackupFile-wal" -Force
    }
    if (Test-Path $shmFile) {
        Copy-Item $shmFile "$BackupFile-shm" -Force
    }
    
    Write-Host "✅ 文件复制备份完成" -ForegroundColor Green
}

# ----------------------------------------------------------------------------
# Step 4: 清理过期备份
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "[4/4] 清理过期备份（保留 $Retention 天）..." -ForegroundColor Yellow

$cutoffDate = (Get-Date).AddDays(-$Retention)
$oldBackups = Get-ChildItem -Path $BackupDir -Filter "monitor-*.db" | 
    Where-Object { $_.CreationTime -lt $cutoffDate }

if ($oldBackups.Count -gt 0) {
    foreach ($backup in $oldBackups) {
        Remove-Item $backup.FullName -Force
        # 同时删除相关的 WAL 和 SHM 文件
        Remove-Item "$($backup.FullName)-wal" -Force -ErrorAction SilentlyContinue
        Remove-Item "$($backup.FullName)-shm" -Force -ErrorAction SilentlyContinue
        Write-Host "   删除: $($backup.Name)" -ForegroundColor Gray
    }
    Write-Host "✅ 已清理 $($oldBackups.Count) 个过期备份" -ForegroundColor Green
} else {
    Write-Host "✅ 无过期备份需要清理" -ForegroundColor Green
}

# ----------------------------------------------------------------------------
# 显示备份列表
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  备份完成！" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$allBackups = Get-ChildItem -Path $BackupDir -Filter "monitor-*.db" | Sort-Object CreationTime -Descending
Write-Host "📁 当前备份列表:" -ForegroundColor Yellow
foreach ($backup in $allBackups) {
    $size = [math]::Round($backup.Length / 1KB, 2)
    Write-Host "   $($backup.Name) - $size KB - $($backup.CreationTime.ToString('yyyy-MM-dd HH:mm:ss'))"
}

$totalSize = ($allBackups | Measure-Object -Property Length -Sum).Sum
Write-Host ""
Write-Host "   总计: $($allBackups.Count) 个备份, $([math]::Round($totalSize / 1MB, 2)) MB" -ForegroundColor Gray
Write-Host ""
