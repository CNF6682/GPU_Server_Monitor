# Optimizing1 升级指南 (v1.0 → v1.1)

本文档指导您将监控系统从 v1.0 升级到 v1.1，包含新增的历史页面、多GPU展示和代理端口转发功能。

---

## 升级概览

### 新增功能
| 功能 | 说明 |
|------|------|
| **历史信息页** | 侧边栏新增「历史」入口，查看 `samples_hourly` 历史数据 |
| **多GPU展示** | 显示每块GPU的使用率/显存/温度 |
| **代理端口转发** | Linux Agent 通过 SSH 隧道访问中心节点代理 |

### 数据库变更
| 表 | 新增字段 | 说明 |
|-----|----------|------|
| `servers` | `proxy_config` | 代理转发配置（JSON） |
| `samples_hourly` | `gpu_details` | 多GPU历史明细（JSON） |

---

## 升级步骤

### 前置条件
- ✅ 已备份 `monitor.db` 数据库
- ✅ Aggregator 服务已停止
- ✅ 安装 SQLite3（PATH 可用）

### Step 1: 停止服务

```powershell
# 停止 Aggregator 服务
net stop MonitorAggregator

# 或使用 NSSM
nssm stop MonitorAggregator
```

### Step 2: 备份数据库

```powershell
# 手动备份
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item "d:\dhga\server\ops\monitor\data\monitor.db" `
          "d:\dhga\server\ops\monitor\backup\monitor-pre-v1.1-$timestamp.db"
```

### Step 3: 执行数据库迁移

**方式 A：使用升级脚本（推荐）**

```powershell
cd d:\dhga\server\ops\monitor\scripts
.\upgrade-to-v1.1.ps1
```

**方式 B：手动执行 SQL**

```powershell
cd d:\dhga\server\ops\monitor
sqlite3.exe data\monitor.db < scripts\migration-v1.1.sql
```

### Step 4: 验证迁移结果

```powershell
sqlite3.exe d:\dhga\server\ops\monitor\data\monitor.db "PRAGMA table_info(servers);"
# 应看到 proxy_config 字段

sqlite3.exe d:\dhga\server\ops\monitor\data\monitor.db "PRAGMA table_info(samples_hourly);"
# 应看到 gpu_details 字段

sqlite3.exe d:\dhga\server\ops\monitor\data\monitor.db "SELECT * FROM schema_migrations;"
# 应看到版本 1.1.0
```

### Step 5: 更新代码

```powershell
# 拉取最新代码（根据实际版本控制）
cd d:\dhga\server
git pull origin main
```

### Step 6: 启动服务

```powershell
# 启动 Aggregator 服务
net start MonitorAggregator

# 或使用 NSSM
nssm start MonitorAggregator
```

### Step 7: 验证功能

1. **访问前端**：打开 `http://localhost:8080`
2. **检查历史页**：点击侧边栏「历史」
3. **检查多GPU**：进入有GPU服务器的详情页

---

## 代理转发配置（可选）

如需启用代理转发功能，请参考 [proxy-setup-guide.md](proxy-setup-guide.md)。

### 快速配置

**1. Windows 中心节点**

```powershell
# 以管理员身份运行
.\scripts\setup-openssh-server.ps1
```

**2. Linux Agent 服务器**

```bash
# 生成 SSH 密钥并配置
./scripts/setup-ssh-keys.sh --host <中心节点IP>
```

**3. 通过 API 配置代理**

```bash
curl -X PUT "http://localhost:8080/api/servers/1/proxy" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "enabled": true,
      "server_listen_port": 8080,
      "center_proxy_port": 7879,
      "center_ssh_host": "10.0.0.2",
      "center_ssh_port": 22,
      "center_ssh_user": "dhga",
      "identity_file": "/home/dhga/.ssh/id_ed25519_monitor"
    },
    "action": "start"
  }'
```

---

## 回滚方法

如遇问题需要回滚：

### 方式 A：从备份恢复

```powershell
net stop MonitorAggregator

Copy-Item "d:\dhga\server\ops\monitor\backup\monitor-pre-v1.1-*.db" `
          "d:\dhga\server\ops\monitor\data\monitor.db" -Force

net start MonitorAggregator
```

### 方式 B：执行回滚脚本

```powershell
net stop MonitorAggregator

sqlite3.exe d:\dhga\server\ops\monitor\data\monitor.db < scripts\rollback-v1.1.sql

net start MonitorAggregator
```

> ⚠️ **注意**：回滚会移除 `proxy_config` 和 `gpu_details` 字段中的所有数据。

---

## 常见问题

### Q: 迁移报错 "duplicate column name"

A: 该字段已存在，可以忽略此错误。升级脚本已处理此情况。

### Q: 升级后前端显示异常

A: 清除浏览器缓存（Ctrl+Shift+R）或硬刷新。

### Q: 代理功能无法启动

A: 请确保：
1. Windows OpenSSH Server 已安装并运行
2. Linux Agent 的公钥已添加到中心节点
3. 防火墙允许 TCP 22

详见 [proxy-troubleshooting.md](proxy-troubleshooting.md)

---

## 升级检查清单

- [ ] 数据库已备份
- [ ] 迁移脚本执行成功
- [ ] `proxy_config` 字段存在
- [ ] `gpu_details` 字段存在
- [ ] `schema_migrations` 版本为 1.1.0
- [ ] Aggregator 服务正常运行
- [ ] 前端可正常访问
- [ ] 历史页功能正常
- [ ] 多GPU展示正常（如适用）
- [ ] 代理转发正常（如配置）
