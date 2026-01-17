# ============================================================================
# 数据库初始化脚本
# 
# 用法: .\init-db.ps1 [-Force]
# 
# 参数:
#   -Force    强制重新初始化（会删除现有数据库）
# 
# 前置条件:
#   - 安装 SQLite3（sqlite3.exe 在 PATH 中）
# ============================================================================

param(
    [switch]$Force
)

# 配置
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MonitorDir = Split-Path -Parent $ScriptDir
$DataDir = Join-Path $MonitorDir "data"
$SchemaFile = Join-Path $MonitorDir "schema.sql"
$DbFile = Join-Path $DataDir "monitor.db"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  监控系统数据库初始化" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ----------------------------------------------------------------------------
# Step 1: 检查 SQLite3 是否可用
# ----------------------------------------------------------------------------
Write-Host "[1/4] 检查 SQLite3..." -ForegroundColor Yellow

# 尝试多个可能的路径
$sqlite3Paths = @(
    "sqlite3.exe",                                          # PATH 中
    "C:\Program Files\SQLite\sqlite3.exe",                  # 标准安装路径
    "C:\sqlite\sqlite3.exe",                                # 常见安装路径
    (Join-Path $env:LOCALAPPDATA "Programs\sqlite3.exe")   # 用户目录
)

$sqlite3 = $null
foreach ($path in $sqlite3Paths) {
    if (Get-Command $path -ErrorAction SilentlyContinue) {
        $sqlite3 = $path
        break
    }
}

if (-not $sqlite3) {
    Write-Host "❌ 错误: 未找到 SQLite3" -ForegroundColor Red
    Write-Host ""
    Write-Host "请安装 SQLite3:" -ForegroundColor Yellow
    Write-Host "  1. 访问 https://sqlite.org/download.html" 
    Write-Host "  2. 下载 sqlite-tools-win-x64-*.zip"
    Write-Host "  3. 解压并将 sqlite3.exe 路径添加到 PATH"
    Write-Host ""
    Write-Host "或使用 winget 安装:" -ForegroundColor Yellow
    Write-Host "  winget install SQLite.SQLite"
    exit 1
}

$sqliteVersion = & $sqlite3 --version 2>&1
Write-Host "✅ SQLite3: $sqliteVersion" -ForegroundColor Green

# ----------------------------------------------------------------------------
# Step 2: 检查 schema.sql 是否存在
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/4] 检查 schema 文件..." -ForegroundColor Yellow

if (-not (Test-Path $SchemaFile)) {
    Write-Host "❌ 错误: Schema 文件不存在: $SchemaFile" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Schema 文件: $SchemaFile" -ForegroundColor Green

# ----------------------------------------------------------------------------
# Step 3: 创建目录
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "[3/4] 创建数据目录..." -ForegroundColor Yellow

if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    Write-Host "✅ 创建目录: $DataDir" -ForegroundColor Green
} else {
    Write-Host "✅ 目录已存在: $DataDir" -ForegroundColor Green
}

# ----------------------------------------------------------------------------
# Step 4: 初始化数据库
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "[4/4] 初始化数据库..." -ForegroundColor Yellow

if (Test-Path $DbFile) {
    if ($Force) {
        Write-Host "⚠️  删除现有数据库（-Force 模式）..." -ForegroundColor Yellow
        
        # 删除数据库及相关文件
        Remove-Item $DbFile -Force -ErrorAction SilentlyContinue
        Remove-Item "$DbFile-shm" -Force -ErrorAction SilentlyContinue
        Remove-Item "$DbFile-wal" -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "⚠️  数据库已存在: $DbFile" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "如需重新初始化，请使用 -Force 参数:" -ForegroundColor Yellow
        Write-Host "  .\init-db.ps1 -Force"
        Write-Host ""
        Write-Host "正在检查并更新 schema（幂等操作）..." -ForegroundColor Yellow
    }
}

# 执行 schema.sql
try {
    # 读取 schema 内容
    $schemaContent = Get-Content $SchemaFile -Raw
    
    # 执行 SQL
    $schemaContent | & $sqlite3 $DbFile
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 数据库初始化成功: $DbFile" -ForegroundColor Green
    } else {
        throw "SQLite3 执行失败，退出码: $LASTEXITCODE"
    }
} catch {
    Write-Host "❌ 错误: 数据库初始化失败" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# ----------------------------------------------------------------------------
# 显示表结构
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  初始化完成！" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "📊 数据表列表:" -ForegroundColor Yellow
& $sqlite3 $DbFile ".tables"

Write-Host ""
Write-Host "📁 数据库信息:" -ForegroundColor Yellow
$dbInfo = Get-Item $DbFile
Write-Host "  路径: $DbFile"
Write-Host "  大小: $([math]::Round($dbInfo.Length / 1KB, 2)) KB"
Write-Host "  创建时间: $($dbInfo.CreationTime)"

Write-Host ""
Write-Host "📌 下一步操作:" -ForegroundColor Yellow
Write-Host "  1. 配置 config.yaml"
Write-Host "  2. 部署 Agent 到 Linux 服务器"
Write-Host "  3. 启动 Aggregator 服务"
Write-Host ""
