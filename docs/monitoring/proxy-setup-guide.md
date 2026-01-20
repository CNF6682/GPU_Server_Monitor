# 代理端口转发配置指南

本文档详细说明如何配置监控系统的代理端口转发功能，使 Linux Agent 服务器能够通过 SSH 隧道访问 Windows 中心节点上的代理服务。

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        校园网/LAN                                │
│                                                                  │
│  ┌──────────────────┐     SSH 隧道      ┌──────────────────────┐ │
│  │  Linux Server    │ ═══════════════════▶│ Windows 中心节点     │ │
│  │                  │                    │                      │ │
│  │ ┌──────────────┐ │                    │ ┌──────────────────┐ │ │
│  │ │ 应用程序     │ │                    │ │ OpenSSH Server   │ │ │
│  │ │ ↓ 请求 ↓     │ │                    │ │ (TCP 22)         │ │ │
│  │ │              │ │                    │ └────────┬─────────┘ │ │
│  │ │ ↓ 127.0.0.1:8080 │ ══════════════════════▶     ↓           │ │
│  │ └──────────────┘ │                    │ ┌────────▼─────────┐ │ │
│  │                  │                    │ │ 代理服务         │ │ │
│  │ monitor-agent    │   ─────────────▶   │ │ (127.0.0.1:7879) │ │ │
│  │ (代理转发模块)   │   状态上报/控制    │ │                  │ │ │
│  └──────────────────┘                    │ └──────────────────┘ │ │
│                                          │                      │ │
│                                          │ monitor-aggregator   │ │
│                                          │ (API + Dashboard)    │ │
│                                          └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 工作原理

1. Linux Agent 使用 SSH 本地端口转发（`ssh -L`）
2. 在 Agent 服务器上监听 `127.0.0.1:8080`
3. 所有发往该端口的请求通过 SSH 隧道转发到中心节点的 `127.0.0.1:7879`
4. 仅绑定 `127.0.0.1`，不暴露外网

---

## 配置步骤

### 步骤 1：Windows 中心节点配置

#### 1.1 安装 OpenSSH Server

**方式 A：一键脚本（推荐）**

```powershell
# 以管理员身份运行 PowerShell
cd d:\dhga\server\ops\monitor\scripts
.\setup-openssh-server.ps1
```

**方式 B：手动安装**

```powershell
# 检查安装状态
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'

# 安装 OpenSSH Server
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# 启动服务
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
```

#### 1.2 配置防火墙

```powershell
# 允许 SSH 入站（默认端口 22）
New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" `
    -DisplayName "OpenSSH Server (sshd)" `
    -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort 22

# 仅允许指定 IP（推荐）
New-NetFirewallRule -Name "OpenSSH-Server-In-TCP-Restricted" `
    -DisplayName "OpenSSH Server (sshd) - Restricted" `
    -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort 22 `
    -RemoteAddress "10.0.0.0/8,192.168.0.0/16"
```

#### 1.3 确保代理服务运行

确保中心节点的代理服务（如 Clash、v2ray 等）正在运行，并监听 `127.0.0.1:7879`。

```powershell
# 检查端口占用
netstat -an | findstr ":7879"
```

---

### 步骤 2：Linux Agent 配置

#### 2.1 生成 SSH 密钥

**方式 A：使用配置脚本（推荐）**

```bash
cd /opt/monitor-agent/scripts  # 或脚本所在位置
chmod +x setup-ssh-keys.sh
./setup-ssh-keys.sh --host 192.168.1.100 --user dhga
```

**方式 B：手动生成**

```bash
# 生成 ed25519 密钥（无密码）
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_monitor -C "monitor-proxy" -N ""

# 设置权限
chmod 600 ~/.ssh/id_ed25519_monitor
chmod 644 ~/.ssh/id_ed25519_monitor.pub

# 显示公钥（需复制到 Windows）
cat ~/.ssh/id_ed25519_monitor.pub
```

#### 2.2 将公钥添加到 Windows

在 Windows 中心节点上：

```powershell
# 普通用户
$pubkey = "ssh-ed25519 AAAA... monitor-proxy"
Add-Content -Path "$env:USERPROFILE\.ssh\authorized_keys" -Value $pubkey

# 管理员用户（需要管理员权限）
$pubkey = "ssh-ed25519 AAAA... monitor-proxy"
Add-Content -Path "C:\ProgramData\ssh\administrators_authorized_keys" -Value $pubkey
```

#### 2.3 测试 SSH 连接

```bash
# 测试连接（首次需确认 host key）
ssh -i ~/.ssh/id_ed25519_monitor -p 22 dhga@192.168.1.100 "echo 'SSH连接成功!'"
```

---

### 步骤 3：配置 Agent 代理转发

#### 3.1 更新 Agent 配置

编辑 `/etc/monitor-agent/config.yaml`：

```yaml
node_id: "srv-01"
listen: "0.0.0.0:9109"
token: "your-token-here"

# 代理转发配置
proxy:
  enabled: true
  server_listen_port: 8080      # Agent 本地监听端口
  center_proxy_port: 7879       # 中心节点代理端口
  center_ssh_host: "192.168.1.100"
  center_ssh_port: 22
  center_ssh_user: "dhga"
  identity_file: "/home/monitor/.ssh/id_ed25519_monitor"
  strict_host_key_checking: true
  auto_start: true              # Agent 启动时自动启动代理
```

#### 3.2 通过 API 配置（可选）

也可以通过 Aggregator API 配置：

```bash
# 保存配置并启动
curl -X PUT "http://aggregator:8080/api/servers/1/proxy" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "enabled": true,
      "server_listen_port": 8080,
      "center_proxy_port": 7879,
      "center_ssh_host": "192.168.1.100",
      "center_ssh_port": 22,
      "center_ssh_user": "dhga",
      "identity_file": "/home/monitor/.ssh/id_ed25519_monitor",
      "strict_host_key_checking": true,
      "auto_start": true
    },
    "action": "start"
  }'
```

---

### 步骤 4：验证代理功能

#### 4.1 检查代理状态

```bash
# 通过 Agent API 查询状态
curl http://localhost:9109/v1/proxy/status

# 预期响应
{
  "status": "connected",
  "pid": 12345,
  "listen_port": 8080,
  "target": "127.0.0.1:7879",
  "last_error": null,
  "connected_since": "2026-01-20T10:00:00Z",
  "retry_count": 0
}
```

#### 4.2 测试代理连接

```bash
# 使用 curl 通过代理访问
curl -x http://127.0.0.1:8080 https://example.com

# 或设置环境变量
export http_proxy=http://127.0.0.1:8080
export https_proxy=http://127.0.0.1:8080
curl https://example.com
```

---

## 配置参考

### proxy_config 字段说明

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `enabled` | bool | 是 | false | 是否启用代理 |
| `server_listen_port` | int | 是 | - | Agent 本地监听端口 |
| `center_proxy_port` | int | 是 | - | 中心节点代理端口 |
| `center_ssh_host` | string | 是 | - | 中心节点 SSH 地址 |
| `center_ssh_port` | int | 否 | 22 | 中心节点 SSH 端口 |
| `center_ssh_user` | string | 是 | - | SSH 用户名 |
| `identity_file` | string | 是 | - | SSH 私钥路径 |
| `strict_host_key_checking` | bool | 否 | true | 严格检查 host key |
| `auto_start` | bool | 否 | false | Agent 启动时自动启动 |

### Agent API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/proxy/status` | GET | 获取代理状态 |
| `/v1/proxy/start` | POST | 启动/重启代理 |
| `/v1/proxy/stop` | POST | 停止代理 |

### Aggregator API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/servers/{id}/proxy` | GET | 获取配置+状态 |
| `/api/servers/{id}/proxy` | PUT | 保存配置+控制 |

---

## 安全建议

### 1. 仅绑定本地地址

默认配置仅绑定 `127.0.0.1`，确保代理不暴露给其他机器。

### 2. 使用专用 SSH 密钥

- 为代理转发创建独立密钥对
- 不要复用 root 或管理员的密钥
- 设置密钥文件权限为 600

### 3. 限制 SSH 访问

```powershell
# Windows 防火墙限制来源 IP
New-NetFirewallRule -Name "SSH-Monitor-Only" `
    -DisplayName "SSH for Monitor Agents Only" `
    -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort 22 `
    -RemoteAddress "10.0.0.101,10.0.0.102,10.0.0.103"
```

### 4. 禁用密码认证

确保 `sshd_config` 中：
```
PasswordAuthentication no
PubkeyAuthentication yes
```

---

## 故障排查

遇到问题请参考 [proxy-troubleshooting.md](proxy-troubleshooting.md)。

### 快速检查

```bash
# 1. 检查 SSH 连接
ssh -v -i ~/.ssh/id_ed25519_monitor -p 22 dhga@192.168.1.100 "echo OK"

# 2. 检查端口监听
netstat -tlnp | grep 8080

# 3. 检查 Agent 日志
journalctl -u monitor-agent -f

# 4. 测试端口转发
ssh -N -L 8080:127.0.0.1:7879 -i ~/.ssh/id_ed25519_monitor dhga@192.168.1.100
```
