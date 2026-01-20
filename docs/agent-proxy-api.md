# Agent 代理转发 API 文档

> 本文档描述 Monitor Agent 的代理转发功能 API 接口

---

## 概述

代理转发功能允许 Linux 服务器通过 SSH 隧道访问 Windows 中心节点的代理服务。Agent 会在本地启动一个 SSH 本地端口转发，将本地端口映射到中心节点的代理端口。

### 核心机制

```bash
ssh -N -L 127.0.0.1:<server_listen_port>:127.0.0.1:<center_proxy_port> \
    user@center_host -p 22 -i ~/.ssh/id_ed25519 \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=yes
```

### 可靠性保障

- **进程管理**：使用 `asyncio.subprocess` 管理 SSH 进程，跟踪 PID
- **重连策略**：指数退避重连（1s → 2s → 4s → 8s → 16s → 32s → 60s 最大）
- **错误处理**：识别端口占用、认证失败、网络不可达等错误
- **日志记录**：连接/断线事件（INFO）+ 错误详情（ERROR）

### 安全措施

- **默认绑定**：仅绑定 `127.0.0.1`，不暴露外网
- **强制密钥认证**：不支持密码认证
- **配置文件权限**：建议设置为 600

---

## API 端点

### 1. 获取代理状态

**端点**: `GET /v1/proxy/status`

**认证**: 需要 Bearer Token

**描述**: 获取代理转发的当前状态

#### 请求示例

```bash
curl -H "Authorization: Bearer <token>" \
     http://localhost:9109/v1/proxy/status
```

#### 响应格式

```json
{
  "status": "connected",
  "pid": 12345,
  "listen_port": 8080,
  "target": "127.0.0.1:7879",
  "last_error": null,
  "connected_since": "2026-01-20T10:30:00Z",
  "retry_count": 0
}
```

#### 状态字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 代理状态（见下表） |
| `pid` | int \| null | SSH 进程 PID |
| `listen_port` | int \| null | 本地监听端口 |
| `target` | string \| null | 目标地址（格式：`127.0.0.1:port`） |
| `last_error` | string \| null | 最后一次错误信息 |
| `connected_since` | string \| null | 连接建立时间（ISO 8601 格式） |
| `retry_count` | int | 当前重试次数 |

#### 状态值说明

| 状态 | 说明 |
|------|------|
| `disabled` | 代理功能未启用（配置中 `enabled: false`） |
| `stopped` | 代理已停止（手动停止或未启动） |
| `connecting` | 正在连接中 |
| `connected` | 已连接，代理正常工作 |
| `error` | 连接失败或异常断开 |

---

### 2. 启动代理转发

**端点**: `POST /v1/proxy/start`

**认证**: 需要 Bearer Token

**描述**: 启动或重启代理转发服务。如果已经在运行，会先停止再启动。

#### 请求示例

```bash
# 使用配置文件中的配置启动
curl -X POST \
     -H "Authorization: Bearer <token>" \
     http://localhost:9109/v1/proxy/start

# 使用自定义配置启动（覆盖配置文件）
curl -X POST \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "config": {
         "enabled": true,
         "server_listen_port": 8080,
         "center_proxy_port": 7879,
         "center_ssh_host": "192.168.1.100",
         "center_ssh_port": 22,
         "center_ssh_user": "dhga",
         "identity_file": "/home/monitor/.ssh/id_ed25519",
         "strict_host_key_checking": true,
         "auto_start": false
       }
     }' \
     http://localhost:9109/v1/proxy/start
```

#### 请求体（可选）

```json
{
  "config": {
    "enabled": true,
    "server_listen_port": 8080,
    "center_proxy_port": 7879,
    "center_ssh_host": "192.168.1.100",
    "center_ssh_port": 22,
    "center_ssh_user": "dhga",
    "identity_file": "/home/monitor/.ssh/id_ed25519",
    "strict_host_key_checking": true,
    "auto_start": false
  }
}
```

#### 响应格式

返回与 `GET /v1/proxy/status` 相同的格式。

#### 错误响应

**400 Bad Request** - 配置错误

```json
{
  "detail": "proxy is disabled in config"
}
```

**500 Internal Server Error** - SSH 客户端未安装

```json
{
  "detail": "ssh binary not found (openssh-client required)"
}
```

---

### 3. 停止代理转发

**端点**: `POST /v1/proxy/stop`

**认证**: 需要 Bearer Token

**描述**: 优雅停止代理转发服务。先发送 SIGTERM，等待 5 秒，如果进程仍未退出则发送 SIGKILL。

#### 请求示例

```bash
curl -X POST \
     -H "Authorization: Bearer <token>" \
     http://localhost:9109/v1/proxy/stop
```

#### 响应格式

返回与 `GET /v1/proxy/status` 相同的格式，状态将变为 `stopped` 或 `disabled`。

---

## 常见错误码

### PORT_IN_USE

**错误信息**: `PORT_IN_USE: 127.0.0.1:8080`

**原因**: 本地监听端口已被占用

**解决方案**:
1. 检查端口占用：`sudo lsof -i :8080`
2. 停止占用端口的进程或更改配置中的 `server_listen_port`

### AUTH_FAILED

**错误信息**: `Permission denied (publickey)`

**原因**: SSH 密钥认证失败

**解决方案**:
1. 确认私钥文件存在且权限正确：`ls -l ~/.ssh/id_ed25519`
2. 确认公钥已添加到中心节点：`ssh-copy-id -i ~/.ssh/id_ed25519.pub user@center_host`
3. 测试 SSH 连接：`ssh -i ~/.ssh/id_ed25519 user@center_host`

### NETWORK_UNREACHABLE

**错误信息**: `Connection refused` 或 `No route to host`

**原因**: 无法连接到中心节点

**解决方案**:
1. 检查网络连通性：`ping center_host`
2. 检查防火墙规则
3. 确认中心节点 SSH 服务正在运行：`systemctl status sshd`

---

## 使用示例

### 场景 1：首次配置并启动代理

```bash
# 1. 生成 SSH 密钥对
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_monitor -C "monitor-proxy"

# 2. 将公钥复制到中心节点
ssh-copy-id -i ~/.ssh/id_ed25519_monitor.pub dhga@192.168.1.100

# 3. 测试 SSH 连接
ssh -i ~/.ssh/id_ed25519_monitor dhga@192.168.1.100 "echo 'Connection OK'"

# 4. 配置 Agent（编辑 /etc/monitor-agent/config.yaml）
# 添加 proxy 配置块

# 5. 重启 Agent 服务
sudo systemctl restart monitor-agent

# 6. 启动代理转发
curl -X POST \
     -H "Authorization: Bearer <token>" \
     http://localhost:9109/v1/proxy/start

# 7. 检查状态
curl -H "Authorization: Bearer <token>" \
     http://localhost:9109/v1/proxy/status
```

### 场景 2：测试代理是否正常工作

```bash
# 1. 检查代理状态
curl -H "Authorization: Bearer <token>" \
     http://localhost:9109/v1/proxy/status

# 2. 测试本地代理端口（假设 server_listen_port=8080）
curl -x http://127.0.0.1:8080 https://www.google.com

# 3. 查看 Agent 日志
sudo journalctl -u monitor-agent -f
```

### 场景 3：处理连接失败

```bash
# 1. 查看详细错误信息
curl -H "Authorization: Bearer <token>" \
     http://localhost:9109/v1/proxy/status | jq '.last_error'

# 2. 手动测试 SSH 连接
ssh -v -N -L 127.0.0.1:8080:127.0.0.1:7879 \
    dhga@192.168.1.100 -p 22 \
    -i ~/.ssh/id_ed25519_monitor

# 3. 检查端口占用
sudo lsof -i :8080

# 4. 重启代理
curl -X POST -H "Authorization: Bearer <token>" \
     http://localhost:9109/v1/proxy/stop
curl -X POST -H "Authorization: Bearer <token>" \
     http://localhost:9109/v1/proxy/start
```

---

## 配置参考

完整的代理配置示例（在 `/etc/monitor-agent/config.yaml` 中）：

```yaml
proxy:
  enabled: true
  server_listen_port: 8080
  center_proxy_port: 7879
  center_ssh_host: "192.168.1.100"
  center_ssh_port: 22
  center_ssh_user: "dhga"
  identity_file: "/home/monitor/.ssh/id_ed25519_monitor"
  strict_host_key_checking: true
  auto_start: false
```

### 配置字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `enabled` | bool | 是 | false | 是否启用代理功能 |
| `server_listen_port` | int | 是 | - | 本地监听端口 |
| `center_proxy_port` | int | 是 | - | 中心节点代理端口 |
| `center_ssh_host` | string | 是 | - | 中心节点 SSH 地址 |
| `center_ssh_port` | int | 否 | 22 | 中心节点 SSH 端口 |
| `center_ssh_user` | string | 是 | - | SSH 用户名 |
| `identity_file` | string | 是 | - | SSH 私钥路径 |
| `strict_host_key_checking` | bool | 否 | true | 是否严格检查 host key |
| `auto_start` | bool | 否 | false | Agent 启动时自动启动代理 |

---

## 注意事项

1. **安全性**
   - 代理仅绑定 `127.0.0.1`，不会暴露到外网
   - 必须使用 SSH 密钥认证，不支持密码认证
   - 建议私钥文件权限设置为 600：`chmod 600 ~/.ssh/id_ed25519_monitor`

2. **可靠性**
   - 连接断开后会自动重连，使用指数退避策略
   - 最大重试间隔为 60 秒
   - 重启 Agent 不会影响已建立的代理连接（除非配置了 `auto_start: true`）

3. **性能**
   - SSH 隧道开销较小，适合中等流量场景
   - 不建议用于高并发或大流量场景

4. **故障排查**
   - 查看 Agent 日志：`sudo journalctl -u monitor-agent -f`
   - 检查 SSH 连接：手动执行 SSH 命令测试
   - 验证端口可用性：`sudo lsof -i :<port>`
