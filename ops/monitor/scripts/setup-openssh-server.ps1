# ============================================================================
# Windows OpenSSH Server 一键配置脚本
# 
# 用法: .\setup-openssh-server.ps1 [-Port PORT] [-AllowedIPs IPs] [-Force]
# 
# 参数:
#   -Port          SSH 端口（默认: 22）
#   -AllowedIPs    允许连接的 IP 地址（逗号分隔，默认: 任意）
#   -Force         强制重新安装
#   -SkipFirewall  跳过防火墙配置
# 
# 说明:
#   此脚本用于在 Windows 中心节点上安装和配置 OpenSSH Server，
#   以便 Linux Agent 能够通过 SSH 隧道进行代理端口转发。
# 
# 前置条件:
#   - Windows 10 1809+ / Windows Server 2019+
#   - 以管理员身份运行
# ============================================================================

#Requires -RunAsAdministrator

param(
    [int]$Port = 22,
    [string]$AllowedIPs = "",
    [switch]$Force,
    [switch]$SkipFirewall
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------
$SSHDir = "$env:ProgramData\ssh"
$SSHDConfig = "$SSHDir\sshd_config"
$AuthorizedKeysFile = "$SSHDir\administrators_authorized_keys"
$ServiceName = "sshd"

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

function Test-OpenSSHInstalled {
    $feature = Get-WindowsCapability -Online | Where-Object { $_.Name -like 'OpenSSH.Server*' }
    return $feature -and $feature.State -eq 'Installed'
}

function Get-OpenSSHVersion {
    try {
        $sshd = & "$env:SystemRoot\System32\OpenSSH\sshd.exe" -? 2>&1 | Select-String "OpenSSH"
        if ($sshd) {
            return $sshd.Line
        }
    } catch {}
    return "Unknown"
}

# ----------------------------------------------------------------------------
# 主程序
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Windows OpenSSH Server 配置" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Step 1: 检查 Windows 版本
Write-Step "1/7" "检查系统版本..."

$osVersion = [System.Environment]::OSVersion.Version
$osBuild = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion").CurrentBuild

if ([int]$osBuild -lt 17763) {
    Write-Error "OpenSSH Server 需要 Windows 10 1809 (Build 17763) 或更高版本"
    Write-Host "当前版本: Build $osBuild"
    exit 1
}

Write-Success "Windows 版本: Build $osBuild"

# Step 2: 安装 OpenSSH Server
Write-Step "2/7" "检查 OpenSSH Server 安装状态..."

if (Test-OpenSSHInstalled) {
    Write-Success "OpenSSH Server 已安装"
    
    if ($Force) {
        Write-Warning "强制重新安装（-Force）..."
        Remove-WindowsCapability -Online -Name (Get-WindowsCapability -Online | Where-Object { $_.Name -like 'OpenSSH.Server*' }).Name
        Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
        Write-Success "重新安装完成"
    }
} else {
    Write-Host "正在安装 OpenSSH Server..."
    
    try {
        Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
        Write-Success "OpenSSH Server 安装完成"
    } catch {
        Write-Error "安装失败: $_"
        Write-Host ""
        Write-Host "手动安装方法:" -ForegroundColor Yellow
        Write-Host "  1. 打开「设置」→「应用」→「可选功能」→「添加功能」"
        Write-Host "  2. 搜索 'OpenSSH 服务器' 并安装"
        exit 1
    }
}

# 显示版本
$sshVersion = Get-OpenSSHVersion
Write-Host "  版本: $sshVersion"

# Step 3: 配置 sshd_config
Write-Step "3/7" "配置 SSH 服务..."

# 创建配置目录
if (-not (Test-Path $SSHDir)) {
    New-Item -ItemType Directory -Path $SSHDir -Force | Out-Null
}

# 备份现有配置
if (Test-Path $SSHDConfig) {
    $backupPath = "$SSHDConfig.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Copy-Item $SSHDConfig $backupPath
    Write-Host "  备份配置: $backupPath"
}

# 读取或创建配置
$defaultConfig = @"
# OpenSSH Server 配置 - 监控系统代理转发
# 生成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

# 基本设置
Port $Port
AddressFamily any
ListenAddress 0.0.0.0
ListenAddress ::

# 认证设置
PubkeyAuthentication yes
PasswordAuthentication no
PermitEmptyPasswords no

# Windows 特定设置
# 管理员用户使用 administrators_authorized_keys
Match Group administrators
    AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys

# 安全设置
PermitRootLogin prohibit-password
StrictModes yes
MaxAuthTries 3
MaxSessions 10

# 子系统
Subsystem sftp sftp-server.exe

# 端口转发设置（代理功能需要）
AllowTcpForwarding yes
GatewayPorts no
AllowStreamLocalForwarding no
PermitTunnel no

# 保持连接
ClientAliveInterval 60
ClientAliveCountMax 3

# 日志
SyslogFacility AUTH
LogLevel INFO
"@

# 写入配置文件
$defaultConfig | Out-File -FilePath $SSHDConfig -Encoding utf8 -Force
Write-Success "配置文件已更新: $SSHDConfig"

# Step 4: 创建 authorized_keys 文件
Write-Step "4/7" "配置授权密钥文件..."

if (-not (Test-Path $AuthorizedKeysFile)) {
    New-Item -ItemType File -Path $AuthorizedKeysFile -Force | Out-Null
    Write-Success "创建密钥文件: $AuthorizedKeysFile"
} else {
    Write-Success "密钥文件已存在: $AuthorizedKeysFile"
}

# 设置正确的权限（只有 Administrators 和 SYSTEM 可访问）
Write-Host "  设置文件权限..."
$acl = Get-Acl $AuthorizedKeysFile
$acl.SetAccessRuleProtection($true, $false)
$acl.Access | ForEach-Object { $acl.RemoveAccessRule($_) } | Out-Null

$adminRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "BUILTIN\Administrators", "FullControl", "Allow")
$systemRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "NT AUTHORITY\SYSTEM", "FullControl", "Allow")

$acl.AddAccessRule($adminRule)
$acl.AddAccessRule($systemRule)
Set-Acl $AuthorizedKeysFile $acl

Write-Success "文件权限已配置"

# Step 5: 配置防火墙
Write-Step "5/7" "配置防火墙规则..."

if ($SkipFirewall) {
    Write-Warning "跳过防火墙配置（-SkipFirewall）"
} else {
    $ruleName = "OpenSSH-Server-In-TCP-$Port"
    
    # 删除旧规则
    Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    
    # 创建新规则
    $ruleParams = @{
        Name = $ruleName
        DisplayName = "OpenSSH Server (sshd) Port $Port"
        Description = "允许 OpenSSH Server 入站连接 (监控系统代理转发)"
        Direction = "Inbound"
        Action = "Allow"
        Protocol = "TCP"
        LocalPort = $Port
        Profile = "Any"
        Enabled = "True"
    }
    
    # 如果指定了允许的 IP
    if ($AllowedIPs) {
        $ruleParams.RemoteAddress = $AllowedIPs.Split(',').Trim()
    }
    
    New-NetFirewallRule @ruleParams | Out-Null
    Write-Success "防火墙规则已创建: $ruleName"
    
    if ($AllowedIPs) {
        Write-Host "  允许的 IP: $AllowedIPs"
    } else {
        Write-Host "  允许: 任意 IP（仅内网使用时建议限制）"
    }
}

# Step 6: 启动服务
Write-Step "6/7" "启动 SSH 服务..."

# 设置服务自动启动
Set-Service -Name $ServiceName -StartupType Automatic

# 启动或重启服务
$service = Get-Service -Name $ServiceName
if ($service.Status -eq 'Running') {
    Restart-Service -Name $ServiceName -Force
    Write-Success "SSH 服务已重启"
} else {
    Start-Service -Name $ServiceName
    Write-Success "SSH 服务已启动"
}

# 验证服务状态
Start-Sleep -Seconds 2
$service = Get-Service -Name $ServiceName
if ($service.Status -ne 'Running') {
    Write-Error "服务启动失败"
    Write-Host "请检查事件查看器中的详细错误"
    exit 1
}

Write-Host "  服务状态: $($service.Status)"

# Step 7: 完成
Write-Step "7/7" "配置完成"

# 获取本机 IP 地址
$localIPs = Get-NetIPAddress -AddressFamily IPv4 | 
    Where-Object { $_.PrefixOrigin -ne 'WellKnown' -and $_.IPAddress -ne '127.0.0.1' } |
    Select-Object -ExpandProperty IPAddress

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  OpenSSH Server 配置成功！" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

Write-Host "📌 服务信息:" -ForegroundColor Yellow
Write-Host "  端口: $Port"
Write-Host "  服务名: $ServiceName"
Write-Host "  状态: Running"
Write-Host ""

Write-Host "📌 本机 IP 地址:" -ForegroundColor Yellow
foreach ($ip in $localIPs) {
    Write-Host "  $ip"
}
Write-Host ""

Write-Host "📌 下一步操作:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. 添加 Linux Agent 的公钥（在本机 PowerShell 中执行）:"
Write-Host ""
Write-Host '   $pubkey = "ssh-ed25519 AAAA... monitor-agent-proxy"' -ForegroundColor DarkGray
Write-Host "   Add-Content -Path `"$AuthorizedKeysFile`" -Value `$pubkey" -ForegroundColor DarkGray
Write-Host ""
Write-Host "2. 在 Linux Agent 上测试连接:"
Write-Host ""
Write-Host "   ssh -p $Port $env:USERNAME@<本机IP>" -ForegroundColor DarkGray
Write-Host ""

Write-Host "📌 相关文件:" -ForegroundColor Yellow
Write-Host "  配置文件: $SSHDConfig"
Write-Host "  授权密钥: $AuthorizedKeysFile"
Write-Host ""

Write-Host "📌 管理命令:" -ForegroundColor Yellow
Write-Host "  查看状态: Get-Service sshd"
Write-Host "  重启服务: Restart-Service sshd"
Write-Host "  查看日志: Get-WinEvent -LogName 'OpenSSH/Operational'"
Write-Host ""

# 提示安全建议
if (-not $AllowedIPs) {
    Write-Host ""
    Write-Host "⚠️  安全提示:" -ForegroundColor Yellow
    Write-Host "  当前允许任意 IP 连接。如仅内网使用，建议限制 IP 范围："
    Write-Host "  .\setup-openssh-server.ps1 -AllowedIPs '10.0.0.0/8,192.168.0.0/16'" -ForegroundColor DarkGray
    Write-Host ""
}
