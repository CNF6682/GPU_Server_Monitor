# 服务器监控系统（Windows 中心节点 + Linux Agent）

轻量级的内网服务器监控方案：Windows 作为中心节点（Aggregator + Dashboard），多台 Linux 作为 Agent，提供 CPU/磁盘/GPU/服务状态的 5s 轮询、每小时入库、前端 Dashboard、可选 SSH 端口转发代理。

## 特色
- **快速部署**：Windows 一键脚本，Linux Agent 支持脚本/手动。
- **轻量存储**：每小时 1 条历史记录，30 天保留，SQLite 即可。
- **多 GPU 兼容**：实时和历史均支持多卡。
- **可选代理转发**：Agent 自建 SSH 隧道访问中心节点的本地代理端口。

## 目录结构
- `ops/monitor/aggregator/`：Windows 中心端（FastAPI + SQLite）
- `ops/monitor/agent/`：Linux Agent（FastAPI）
- `ops/monitor/frontend/`：静态 Dashboard
- `ops/monitor/scripts/`：初始化/备份/健康检查/迁移等脚本
- `docs/monitoring/`：方案、架构、升级与代理配置说明

## 环境依赖
Windows（中心节点）：
- Python 3.11+（建议本地或独立 venv）
- SQLite（已随 Python 自带 CLI 即可）
- OpenSSH Server（仅代理转发场景需要）

Linux（Agent）：
- Python 3.9+（虚拟环境或系统 Python）
- `curl`/`psutil`/`nvidia-smi`（GPU 场景）
- 可选：systemd（服务状态采集）

### Python 依赖（精简）
- Aggregator：`fastapi`、`uvicorn`、`httpx`、`pydantic`、`pydantic-settings`、`aiosqlite`、`apscheduler`
- Agent：`fastapi`、`uvicorn`、`psutil`、`httpx`（GPU 场景需 `nvidia-ml-py` 或调用 `nvidia-smi`）

在各自目录安装：
```bash
# Windows aggregator（推荐 venv）
cd ops/monitor/aggregator
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# Linux agent
cd /opt/monitor-agent           # 你的 agent 路径
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Windows 中心节点快速开始
在 PowerShell 中运行（允许脚本执行，必要时加 `-ExecutionPolicy Bypass`）：

```powershell
cd d:\dhga\server\ops\monitor

# 1) 初始化数据库（幂等）
.\scripts\init-db.ps1

# 2) 安装依赖（在 aggregator 目录创建 venv）
cd .\aggregator
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# 3) 启动服务（包含 API + Dashboard + 定时任务）
cd ..\scripts
.\start-aggregator.ps1
# 停止可用 .\stop-aggregator.ps1
```

访问：`http://localhost:8080`

健康巡检：`.\scripts\health-check.ps1 -Verbose`

### 升级/迁移（v1.1）
已执行 `scripts/migration-v1.1.sql` 添加代理与多 GPU 字段。如新环境需要，运行：
```powershell
cd d:\dhga\server\ops\monitor
sqlite3 data\monitor.db ".read scripts/migration-v1.1.sql"
```

## 添加 Linux Agent
自动脚本（适合可 SSH 的环境）：
```bash
cd d:/dhga/server/ops/monitor/scripts   # Windows Git Bash/WSL
./deploy-agent.sh <server-ip> <node-id> <token> <center-ip>
```

手动（摘要）：
```bash
sudo mkdir -p /opt/monitor-agent /etc/monitor-agent
sudo python3 -m venv /opt/monitor-agent/venv
sudo /opt/monitor-agent/venv/bin/pip install -r /opt/monitor-agent/requirements.txt

cat | sudo tee /etc/monitor-agent/config.yaml <<'EOF'
node_id: "srv-01"
listen: "0.0.0.0:9109"
token: "YOUR_TOKEN"
disks: ["/"]
services_allowlist: []
gpu: "nvidia"
# 可选代理配置见下
EOF

sudo /opt/monitor-agent/venv/bin/python -m monitor_agent.app
# 建议注册为 systemd 服务（略）
```

## 代理转发（SSH 隧道，非必需）
用途：Agent 将本地端口（如 8080）通过 SSH 隧道转发到中心节点的本地代理端口（如 7879）。

前提：
- Windows 开启 OpenSSH Server，端口 22，允许公钥登录。
- 将 Agent 侧公钥写入对应 Windows 用户的 `authorized_keys`（或 `administrators_authorized_keys`）。

配置入口：
- 前端 “服务器管理” → 编辑 → “代理转发配置”
- 或 API：`PUT /api/servers/{id}/proxy`

关键字段：
- `server_listen_port`：Agent 本地监听端口（例 8080）
- `center_proxy_port`：中心节点本地代理端口（例 7879）
- `center_ssh_host` / `center_ssh_port` / `center_ssh_user`
- `identity_file`：Agent 上的私钥路径

常见问题：
- 报 `Permission denied (publickey,...)`：检查 Windows authorized_keys、私钥路径/权限、用户是否命中 Match administrators。
- 初次连接 host key 未知：可暂时关闭“严格 host key 检查”，连通后再开启。

## 维护与排障
- 健康巡检：`ops/monitor/scripts/health-check.ps1 -Verbose`
- 查看日志：`logs/monitor-aggregator/aggregator.log`
- 停止/启动：`ops/monitor/scripts/stop-aggregator.ps1` / `start-aggregator.ps1`
- 备份数据库：`ops/monitor/scripts/backup-db.ps1`

## 更多文档
- 方案与架构：`docs/monitoring/monitoring-plan.md`, `docs/monitoring/architecture.md`
- 代理配置指南：`docs/monitoring/proxy-setup-guide.md`
- 优化与升级：`docs/monitoring/optimizing1-*.md`
