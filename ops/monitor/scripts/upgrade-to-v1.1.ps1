# ============================================================================
# 监控系统升级脚本 v1.0 -> v1.1
# 
# 用法: .\upgrade-to-v1.1.ps1 [-SkipBackup] [-Force]
# 
# 参数:
#   -SkipBackup   跳过备份步骤（不推荐）
#   -Force        强制执行（即使检测到问题）
# 
# 功能:
#   1. 自动备份 monitor.db
#   2. 执行迁移SQL
#   3. 验证表结构
#   4. 显示升级结果
# ============================================================================

param(
    [switch]$SkipBackup,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MonitorDir = Split-Path -Parent $ScriptDir
$DataDir = Join-Path $MonitorDir "data"
$BackupDir = Join-Path $MonitorDir "backup"
$DbFile = Join-Path $DataDir "monitor.db"
$MigrationFile = Join-Path $ScriptDir "migration-v1.1.sql"
$RollbackFile = Join-Path $ScriptDir "rollback-v1.1.sql"

$TargetVersion = "1.1.0"
$BackupTimestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupFile = Join-Path $BackupDir "monitor-pre-v1.1-$BackupTimestamp.db"

# ----------------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------------
function Write-Step {
    param([string]$Step, [string]$Message)
    Write-Host ""
    Write-Host "[$Step] $Message" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

function Write-Warning {
    param([string]$Message)
    Write-Host "⚠️  $Message" -ForegroundColor Yellow
}

function Find-Sqlite3 {
    $paths = @(
        "sqlite3.exe",
        "C:\Program Files\SQLite\sqlite3.exe",
        "C:\sqlite\sqlite3.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\sqlite3.exe")
    )
    foreach ($path in $paths) {
        if (Get-Command $path -ErrorAction SilentlyContinue) {
            return $path
        }
    }
    return $null
}

function Get-CurrentVersion {
    param([string]$Sqlite, [string]$Database)
    try {
        $result = & $Sqlite $Database "SELECT version FROM schema_migrations ORDER BY applied_at DESC LIMIT 1;" 2>&1
        if ($LASTEXITCODE -eq 0 -and $result) {
            return $result.Trim()
        }
    } catch {}
    return "1.0.0"
}

function Test-ColumnExists {
    param([string]$Sqlite, [string]$Database, [string]$Table, [string]$Column)
    $result = & $Sqlite $Database "PRAGMA table_info($Table);" 2>&1
    return $result -match "\b$Column\b"
}

# ----------------------------------------------------------------------------
# 主程序
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  监控系统升级 v1.0 → v1.1" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Step 1: 检查前置条件
Write-Step "1/6" "检查前置条件..."

# 1.1 检查 SQLite3
$sqlite3 = Find-Sqlite3
if (-not $sqlite3) {
    Write-Error "未找到 SQLite3，请先安装"
    exit 1
}
Write-Success "SQLite3: $((& $sqlite3 --version 2>&1) -split ' ' | Select-Object -First 1)"

# 1.2 检查数据库文件
if (-not (Test-Path $DbFile)) {
    Write-Error "数据库不存在: $DbFile"
    Write-Host "请先运行 init-db.ps1 初始化数据库" -ForegroundColor Yellow
    exit 1
}
Write-Success "数据库: $DbFile"

# 1.3 检查迁移脚本
if (-not (Test-Path $MigrationFile)) {
    Write-Error "迁移脚本不存在: $MigrationFile"
    exit 1
}
Write-Success "迁移脚本: $MigrationFile"

# Step 2: 版本检查
Write-Step "2/6" "检查当前版本..."

$currentVersion = Get-CurrentVersion $sqlite3 $DbFile
Write-Host "  当前版本: $currentVersion"
Write-Host "  目标版本: $TargetVersion"

if ($currentVersion -eq $TargetVersion) {
    Write-Warning "数据库已经是 $TargetVersion 版本"
    if (-not $Force) {
        Write-Host "使用 -Force 参数强制重新执行迁移" -ForegroundColor Yellow
        exit 0
    }
}

# 检查字段是否已存在
$proxyConfigExists = Test-ColumnExists $sqlite3 $DbFile "servers" "proxy_config"
$gpuDetailsExists = Test-ColumnExists $sqlite3 $DbFile "samples_hourly" "gpu_details"

if ($proxyConfigExists -or $gpuDetailsExists) {
    Write-Warning "检测到部分字段已存在:"
    if ($proxyConfigExists) { Write-Host "  - servers.proxy_config" }
    if ($gpuDetailsExists) { Write-Host "  - samples_hourly.gpu_details" }
    
    if (-not $Force) {
        Write-Host "使用 -Force 参数强制继续" -ForegroundColor Yellow
        exit 0
    }
}

# Step 3: 备份数据库
Write-Step "3/6" "备份数据库..."

if ($SkipBackup) {
    Write-Warning "已跳过备份（-SkipBackup）"
} else {
    # 创建备份目录
    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    }
    
    # 复制数据库文件
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
    
    $backupSize = [math]::Round((Get-Item $BackupFile).Length / 1KB, 2)
    Write-Success "备份完成: $BackupFile ($backupSize KB)"
}

# Step 4: 执行迁移
Write-Step "4/6" "执行数据库迁移..."

try {
    # 读取并执行迁移SQL
    $migrationContent = Get-Content $MigrationFile -Raw
    
    # 过滤掉已存在字段的 ALTER TABLE 语句（防止报错）
    $statements = $migrationContent -split ';'
    $executedCount = 0
    $skippedCount = 0
    
    foreach ($stmt in $statements) {
        $stmt = $stmt.Trim()
        if ([string]::IsNullOrWhiteSpace($stmt)) { continue }
        if ($stmt -match '^--') { continue }  # 跳过注释行
        
        # 检查是否需要跳过
        $shouldSkip = $false
        if ($stmt -match 'ALTER TABLE servers ADD COLUMN proxy_config' -and $proxyConfigExists) {
            Write-Host "  跳过: servers.proxy_config (已存在)" -ForegroundColor DarkGray
            $skippedCount++
            $shouldSkip = $true
        }
        if ($stmt -match 'ALTER TABLE samples_hourly ADD COLUMN gpu_details' -and $gpuDetailsExists) {
            Write-Host "  跳过: samples_hourly.gpu_details (已存在)" -ForegroundColor DarkGray
            $skippedCount++
            $shouldSkip = $true
        }
        
        if (-not $shouldSkip) {
            # 执行语句
            $result = echo "$stmt;" | & $sqlite3 $DbFile 2>&1
            if ($LASTEXITCODE -ne 0) {
                # 检查是否是重复列错误（可以忽略）
                if ($result -match 'duplicate column name') {
                    Write-Host "  跳过: 字段已存在" -ForegroundColor DarkGray
                    $skippedCount++
                } else {
                    throw "SQL执行失败: $result"
                }
            } else {
                $executedCount++
            }
        }
    }
    
    Write-Success "迁移完成 (执行: $executedCount, 跳过: $skippedCount)"
    
} catch {
    Write-Error "迁移失败: $_"
    
    if (-not $SkipBackup) {
        Write-Host ""
        Write-Host "正在回滚..." -ForegroundColor Yellow
        Copy-Item $BackupFile $DbFile -Force
        if (Test-Path "$BackupFile-wal") {
            Copy-Item "$BackupFile-wal" "$DbFile-wal" -Force
        }
        Write-Success "已从备份恢复数据库"
    }
    
    exit 1
}

# Step 5: 验证迁移结果
Write-Step "5/6" "验证迁移结果..."

$errors = @()

# 验证 servers.proxy_config
if (-not (Test-ColumnExists $sqlite3 $DbFile "servers" "proxy_config")) {
    $errors += "servers.proxy_config 字段未创建"
}

# 验证 samples_hourly.gpu_details
if (-not (Test-ColumnExists $sqlite3 $DbFile "samples_hourly" "gpu_details")) {
    $errors += "samples_hourly.gpu_details 字段未创建"
}

# 验证版本记录
$newVersion = Get-CurrentVersion $sqlite3 $DbFile
if ($newVersion -ne $TargetVersion) {
    $errors += "版本记录未更新 (期望: $TargetVersion, 实际: $newVersion)"
}

if ($errors.Count -gt 0) {
    Write-Error "验证失败:"
    foreach ($err in $errors) {
        Write-Host "  - $err" -ForegroundColor Red
    }
    exit 1
}

Write-Success "servers.proxy_config - 已创建"
Write-Success "samples_hourly.gpu_details - 已创建"
Write-Success "schema_migrations - 版本 $newVersion"

# Step 6: 完成
Write-Step "6/6" "升级完成"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  升级成功！v1.0.0 → v$TargetVersion" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

# 显示表结构
Write-Host "📊 servers 表新增字段:" -ForegroundColor Yellow
& $sqlite3 $DbFile "PRAGMA table_info(servers);" | Select-String "proxy_config"

Write-Host ""
Write-Host "📊 samples_hourly 表新增字段:" -ForegroundColor Yellow
& $sqlite3 $DbFile "PRAGMA table_info(samples_hourly);" | Select-String "gpu_details"

Write-Host ""
Write-Host "📌 下一步操作:" -ForegroundColor Yellow
Write-Host "  1. 重启 Aggregator 服务"
Write-Host "  2. 配置代理转发（可选）"
Write-Host "  3. 参考 docs/monitoring/proxy-setup-guide.md"
Write-Host ""

if (-not $SkipBackup) {
    Write-Host "📁 备份文件:" -ForegroundColor Yellow
    Write-Host "  $BackupFile"
    Write-Host ""
    Write-Host "如需回滚，执行:" -ForegroundColor Yellow
    Write-Host "  sqlite3 $DbFile < $RollbackFile"
    Write-Host ""
}
