# 代理端口转发故障排查

本文档帮助您诊断和解决代理端口转发功能的常见问题。

---

## 快速诊断

```bash
# 在 Linux Agent 上运行
curl -s http://localhost:9109/v1/proxy/status | python3 -m json.tool
```

根据 `status` 字段判断问题类型：

| status | 含义 | 下一步 |
|--------|------|--------|
| `connected` | 正常运行 | 检查代理本身 |
| `connecting` | 正在连接 | 等待或检查网络 |
| `disconnected` | 已断开 | 查看 `last_error` |
| `error` | 启动失败 | 查看错误详情 |

---

## 常见问题

### 问题 1：SSH 连接被拒绝

**症状**
```
ssh: connect to host 192.168.1.100 port 22: Connection refused
```

**排查步骤**

1. **检查 Windows OpenSSH Server 状态**
   ```powershell
   Get-Service sshd
   # 如未运行，启动服务
   Start-Service sshd
   ```

2. **检查端口监听**
   ```powershell
   netstat -an | findstr ":22"
   # 应看到 0.0.0.0:22 或 [::]:22 LISTENING
   ```

3. **检查防火墙**
   ```powershell
   Get-NetFirewallRule -Name "*ssh*" | Format-Table Name, Enabled, Action
   ```

4. **测试本地连接（在 Windows 上）**
   ```powershell
   ssh localhost
   ```

---

### 问题 2：SSH 认证失败

**症状**
```
Permission denied (publickey)
```

**排查步骤**

1. **验证公钥已添加**
   ```powershell
   # 在 Windows 上检查
   Get-Content "C:\ProgramData\ssh\administrators_authorized_keys"
   # 或
   Get-Content "$env:USERPROFILE\.ssh\authorized_keys"
   ```

2. **检查密钥文件权限（Linux 端）**
   ```bash
   ls -la ~/.ssh/id_ed25519_monitor
   # 应为 -rw------- (600)
   chmod 600 ~/.ssh/id_ed25519_monitor
   ```

3. **检查 authorized_keys 权限（Windows 端）**
   ```powershell
   # administrators_authorized_keys 应只有 Administrators 和 SYSTEM 权限
   icacls "C:\ProgramData\ssh\administrators_authorized_keys"
   ```

4. **使用详细模式测试**
   ```bash
   ssh -vvv -i ~/.ssh/id_ed25519_monitor dhga@192.168.1.100
   # 查看详细的认证过程
   ```

5. **检查 sshd 日志**
   ```powershell
   Get-WinEvent -LogName 'OpenSSH/Operational' | Select-Object -First 20
   ```

---

### 问题 3：端口已被占用

**症状**
```
{"status": "error", "last_error": "PORT_IN_USE"}
```

**排查步骤**

1. **查找占用进程**
   ```bash
   # Linux
   lsof -i :8080
   # 或
   netstat -tlnp | grep 8080
   ```

2. **更换端口**
   
   修改配置中的 `server_listen_port` 为其他端口（如 8081）。

3. **终止占用进程**
   ```bash
   kill <PID>
   ```

---

### 问题 4：网络不可达

**症状**
```
{"status": "error", "last_error": "NETWORK_UNREACHABLE"}
```

**排查步骤**

1. **测试网络连通性**
   ```bash
   ping 192.168.1.100
   ```

2. **测试 SSH 端口**
   ```bash
   nc -zv 192.168.1.100 22
   # 或
   telnet 192.168.1.100 22
   ```

3. **检查路由**
   ```bash
   traceroute 192.168.1.100
   ```

4. **检查 Linux 防火墙**
   ```bash
   # Ubuntu/Debian
   ufw status
   
   # RHEL/CentOS
   firewall-cmd --list-all
   ```

---

### 问题 5：Host Key 验证失败

**症状**
```
Host key verification failed.
```

**排查步骤**

1. **首次连接需确认 host key**
   ```bash
   ssh -i ~/.ssh/id_ed25519_monitor dhga@192.168.1.100
   # 输入 "yes" 接受 host key
   ```

2. **Host key 已变更**
   ```bash
   # 删除旧的 host key
   ssh-keygen -R 192.168.1.100
   # 重新连接
   ssh -i ~/.ssh/id_ed25519_monitor dhga@192.168.1.100
   ```

3. **禁用严格检查（不推荐用于生产）**
   
   配置中设置 `strict_host_key_checking: false`

---

### 问题 6：代理频繁断线重连

**症状**
```
{"status": "connected", "retry_count": 15, ...}
```

**排查步骤**

1. **检查网络稳定性**
   ```bash
   ping -c 100 192.168.1.100 | grep -E "(loss|rtt)"
   ```

2. **增加 KeepAlive 间隔**
   
   Agent 默认 `ServerAliveInterval=30`，如网络不稳定可增加。

3. **检查 Windows 电源管理**
   - 确保网卡未启用节能模式
   - 确保系统不会休眠

4. **查看重连日志**
   ```bash
   journalctl -u monitor-agent | grep -i proxy
   ```

---

### 问题 7：代理连接成功但无法访问外网

**症状**
- `proxy/status` 显示 `connected`
- `curl -x http://127.0.0.1:8080 https://example.com` 失败

**排查步骤**

1. **确认中心节点代理运行中**
   ```powershell
   netstat -an | findstr ":7879"
   # 应看到 127.0.0.1:7879 LISTENING
   ```

2. **在中心节点直接测试代理**
   ```powershell
   $proxy = [System.Net.WebProxy]::new("http://127.0.0.1:7879")
   $client = [System.Net.WebClient]::new()
   $client.Proxy = $proxy
   $client.DownloadString("https://example.com")
   ```

3. **检查代理配置**
   - 代理是否需要认证？
   - 代理是 HTTP 还是 SOCKS5？

4. **手动测试 SSH 隧道**
   ```bash
   # 手动建立隧道
   ssh -N -L 8080:127.0.0.1:7879 -i ~/.ssh/id_ed25519_monitor dhga@192.168.1.100
   
   # 另一个终端测试
   curl -x http://127.0.0.1:8080 https://httpbin.org/ip
   ```

---

## 日志收集

### Linux Agent 日志

```bash
# systemd journal
journalctl -u monitor-agent -n 100 --no-pager

# 实时跟踪
journalctl -u monitor-agent -f

# 保存到文件
journalctl -u monitor-agent --since "1 hour ago" > agent-log.txt
```

### Windows SSH 日志

```powershell
# OpenSSH 事件日志
Get-WinEvent -LogName 'OpenSSH/Operational' -MaxEvents 100 | 
    Format-List TimeCreated, Message

# 启用详细日志（临时）
# 编辑 C:\ProgramData\ssh\sshd_config
# LogLevel DEBUG3
# 重启服务后查看 C:\ProgramData\ssh\logs\sshd.log
```

### 手动 SSH 调试

```bash
# 最详细的调试输出
ssh -vvv -N -L 8080:127.0.0.1:7879 \
    -i ~/.ssh/id_ed25519_monitor \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    dhga@192.168.1.100 2>&1 | tee ssh-debug.log
```

---

## 错误代码参考

| 错误码 | 含义 | 常见原因 |
|--------|------|----------|
| `PORT_IN_USE` | 端口被占用 | 其他程序占用监听端口 |
| `AUTH_FAILED` | 认证失败 | 公钥未配置或权限不对 |
| `NETWORK_UNREACHABLE` | 网络不可达 | 网络故障或防火墙 |
| `HOST_KEY_MISMATCH` | Host key 不匹配 | 中心节点重装或中间人攻击 |
| `CONNECTION_TIMEOUT` | 连接超时 | 网络延迟或防火墙 |
| `SSH_PROCESS_DIED` | SSH 进程意外退出 | 资源不足或被 kill |

---

## 获取帮助

如问题仍未解决，请收集以下信息后联系支持：

1. **Agent 代理状态**
   ```bash
   curl http://localhost:9109/v1/proxy/status
   ```

2. **Agent 配置（隐藏敏感信息）**
   ```bash
   cat /etc/monitor-agent/config.yaml | grep -v token
   ```

3. **最近日志**
   ```bash
   journalctl -u monitor-agent -n 200 --no-pager
   ```

4. **网络测试结果**
   ```bash
   ping -c 5 <center_host>
   nc -zv <center_host> 22
   ssh -vvv -i ~/.ssh/id_ed25519_monitor <user>@<center_host> 2>&1 | head -50
   ```
