# 服务器监控系统部署指南

> 监控 Linux 服务器的 CPU、磁盘、GPU 使用率和服务状态

## 📋 系统概览

```
┌──────────────────────────────────────────────────────────────────┐
│                        校园网 / LAN                              │
│                                                                  │
│  ┌──────────────┐                                                │
│  │ Linux Server │◄───────┐                                       │
│  │ monitor-agent│        │ HTTP (5s 拉取)                         │
│  └──────────────┘        │                                       │
│                          │       ┌───────────────┐               │
│  ┌──────────────┐        ├───────│  Aggregator   │               │
│  │ Linux Server │◄───────┤       │  (Windows)    │               │
│  │ monitor-agent│        │       │  + SQLite DB  │               │
│  └──────────────┘        │       └───────┬───────┘               │
│                          │               │                        │
│  ┌──────────────┐        │               │ HTTP API               │
│  │ Linux Server │◄───────┘               │                        │
│  │ monitor-agent│                    ┌───┴───┐                    │
│  └──────────────┘                    │ 前端   │                    │
│                                      │Dashboard│                   │
│                                      └────────┘                   │
└──────────────────────────────────────────────────────────────────┘
```

**组件说明**:
- **monitor-agent (Linux)**: 轻量级采集代理，提供 HTTP 接口
- **monitor-aggregator (Windows)**: 中心节点，负责数据采集、聚合和 API
- **Frontend**: Web 仪表盘，展示监控数据

---

## 🚀 快速开始

### 1. 初始化数据库

```powershell
# 进入脚本目录
cd d:\dhga\server\ops\monitor\scripts

# 初始化数据库
.\init-db.ps1
```

### 2. 部署 Agent 到 Linux 服务器

```bash
# 从 Windows 执行（需要 Git Bash 或 WSL）
./deploy-agent.sh <server-ip> <node-id> <token> [center-ip]

# 示例
./deploy-agent.sh 10.0.0.101 srv-01 my-secret-token 10.0.0.10
```

### 3. 启动 Aggregator

```powershell
# 确保已安装 Python 依赖
cd d:\dhga\server\ops\monitor\aggregator
pip install -r requirements.txt

# 启动服务
python -m monitor_aggregator
```

### 4. 访问 Dashboard

打开浏览器访问: `http://localhost:8080`

---

## 📁 目录结构

```
ops/monitor/
├── config.yaml                # Aggregator 配置文件
├── schema.sql                 # 数据库初始化脚本
├── README.md                  # 本文档
│
├── agent/                     # Agent 源码（Linux 部署）
│   ├── monitor_agent/
│   ├── requirements.txt
│   └── config.example.yaml
│
├── aggregator/                # Aggregator 源码（Windows）
│   ├── monitor_aggregator/
│   ├── requirements.txt
│   └── service.json
│
├── frontend/                  # 前端文件
│   ├── index.html
│   └── assets/
│
├── data/                      # 数据目录
│   └── monitor.db
│
├── backup/                    # 备份目录
│
└── scripts/                   # 运维脚本
    ├── deploy-agent.sh
    ├── init-db.ps1
    ├── backup-db.ps1
    └── health-check.ps1
```

---

## 📖 分步部署指南

### Step 1: 环境准备

#### Windows 中心节点

1. **Python 3.8+**
   ```powershell
   python --version  # 确认版本
   ```

2. **SQLite3** (用于数据库管理)
   ```powershell
   # 使用 winget 安装
   winget install SQLite.SQLite
   
   # 或手动下载
   # https://sqlite.org/download.html
   ```

#### Linux 服务器

1. **Python 3.8+**
   ```bash
   python3 --version
   ```

2. **curl** (用于健康检查)
   ```bash
   which curl
   ```

### Step 2: 初始化数据库

```powershell
# 切换到脚本目录
cd d:\dhga\server\ops\monitor\scripts

# 执行初始化
.\init-db.ps1

# 如需重新初始化（会删除现有数据）
.\init-db.ps1 -Force
```

**输出示例**:
```
✅ SQLite3: 3.45.0
✅ Schema 文件: d:\dhga\server\ops\monitor\schema.sql
✅ 创建目录: d:\dhga\server\ops\monitor\data
✅ 数据库初始化成功: d:\dhga\server\ops\monitor\data\monitor.db

📊 数据表列表:
events           samples_hourly   servers          service_status
```

### Step 3: 部署 Agent

#### 方式 A: 自动化脚本部署

1. **配置 SSH 免密登录**
   ```bash
   # 在 Windows 上生成密钥（如果没有）
   ssh-keygen -t ed25519
   
   # 复制公钥到目标服务器
   ssh-copy-id root@10.0.0.101
   ```

2. **运行部署脚本**
   ```bash
   cd d:/dhga/server/ops/monitor/scripts
   ./deploy-agent.sh 10.0.0.101 srv-01 $(openssl rand -base64 32) 10.0.0.10
   ```

#### 方式 B: 手动部署

1. **创建用户和目录**
   ```bash
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin monitor-agent
   sudo mkdir -p /opt/monitor-agent /etc/monitor-agent
   ```

2. **上传代码**
   ```bash
   scp -r ops/monitor/agent/* root@10.0.0.101:/opt/monitor-agent/
   ```

3. **安装依赖**
   ```bash
   sudo python3 -m venv /opt/monitor-agent/venv
   sudo /opt/monitor-agent/venv/bin/pip install -r /opt/monitor-agent/requirements.txt
   ```

4. **创建配置文件**
   ```bash
   sudo cat > /etc/monitor-agent/config.yaml << EOF
   node_id: "srv-01"
   listen: "0.0.0.0:9109"
   token: "YOUR_SECRET_TOKEN"
   disks:
     - "/"
   services_allowlist: []
   gpu: "nvidia"
   EOF
   ```

5. **配置 systemd**
   ```bash
   sudo cat > /etc/systemd/system/monitor-agent.service << 'EOF'
   [Unit]
   Description=Monitor Agent
   After=network.target

   [Service]
   Type=simple
   User=root
   ExecStart=/opt/monitor-agent/venv/bin/python -m monitor_agent
   Restart=always
   RestartSec=2

   [Install]
   WantedBy=multi-user.target
   EOF

   sudo systemctl daemon-reload
   sudo systemctl enable --now monitor-agent
   ```

6. **配置防火墙**
   ```bash
   # UFW (Ubuntu)
   sudo ufw allow from 10.0.0.10 to any port 9109 proto tcp
   
   # firewalld (RHEL/CentOS)
   sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=10.0.0.10 port port=9109 protocol=tcp accept'
   sudo firewall-cmd --reload
   ```

### Step 4: 配置 Aggregator

1. **编辑配置文件**
   ```yaml
   # ops/monitor/config.yaml
   database:
     path: "ops/monitor/data/monitor.db"
   
   api:
     host: "0.0.0.0"
     port: 8080
     admin_token: "YOUR_ADMIN_TOKEN"  # 修改为随机字符串
   ```

2. **添加服务器**
   
   通过 API 添加：
   ```powershell
   curl.exe -X POST http://localhost:8080/api/servers `
     -H "Content-Type: application/json" `
     -H "X-Admin-Token: YOUR_ADMIN_TOKEN" `
     -d '{
       "name": "srv-01",
       "host": "10.0.0.101",
       "agent_port": 9109,
       "token": "YOUR_SECRET_TOKEN",
       "services": [],
       "enabled": true
     }'
   ```
   
   或通过前端管理界面添加。

### Step 5: 注册为 Windows 服务

使用 NSSM 将 Aggregator 注册为 Windows 服务：

```powershell
# 安装 NSSM
winget install NSSM.NSSM

# 安装服务
nssm install MonitorAggregator "C:\Python311\python.exe" "-m monitor_aggregator.main"
nssm set MonitorAggregator AppDirectory "d:\dhga\server\ops\monitor\aggregator"
nssm set MonitorAggregator DisplayName "Monitor Aggregator"
nssm set MonitorAggregator Description "Server monitoring aggregator service"

# 启动服务
nssm start MonitorAggregator
```

---

## 🔧 运维操作

### 健康巡检

```powershell
.\scripts\health-check.ps1

# 详细输出
.\scripts\health-check.ps1 -Verbose
```

### 数据库备份

```powershell
# 执行备份（保留 7 天）
.\scripts\backup-db.ps1

# 自定义保留天数
.\scripts\backup-db.ps1 -Retention 14
```

### 定时任务配置

使用 Windows 任务计划程序设置自动备份：

```powershell
# 创建每日备份任务（凌晨 4 点）
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" `
    -Argument "-File d:\dhga\server\ops\monitor\scripts\backup-db.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At 4am
Register-ScheduledTask -TaskName "MonitorDB-Backup" -Action $action -Trigger $trigger
```

---

## ❓ 常见问题

### Q1: Agent 无响应

**症状**: 服务器显示离线

**排查步骤**:
```bash
# 1. 检查服务状态
sudo systemctl status monitor-agent

# 2. 查看日志
sudo journalctl -u monitor-agent -n 50

# 3. 测试端口
curl http://localhost:9109/v1/health

# 4. 检查防火墙
sudo ufw status | grep 9109
```

### Q2: 数据库锁定错误

**症状**: `database is locked` 错误

**解决方案**:
```powershell
# 执行 WAL checkpoint
$sqlite3 = "sqlite3.exe"
& $sqlite3 "ops\monitor\data\monitor.db" "PRAGMA wal_checkpoint(TRUNCATE);"
```

### Q3: GPU 采集失败

**症状**: GPU 数据为空

**排查步骤**:
```bash
# 检查驱动
nvidia-smi

# 检查 nvidia-smi 命令路径
which nvidia-smi

# 手动测试采集
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits
```

### Q4: 前端无法连接 API

**症状**: 浏览器报 CORS 错误

**解决方案**:
1. 确认 `config.yaml` 中 `cors_origins` 包含前端地址
2. 确认 Aggregator 服务正在运行

---

## 📊 API 参考

### 服务器列表
```http
GET /api/servers
```

### 添加服务器
```http
POST /api/servers
Content-Type: application/json
X-Admin-Token: <token>

{
  "name": "srv-01",
  "host": "10.0.0.101",
  "agent_port": 9109,
  "token": "xxx",
  "services": ["nginx.service"],
  "enabled": true
}
```

### 时间序列数据
```http
GET /api/servers/{id}/timeseries?metric=cpu_pct&from=2026-01-17T00:00:00Z&to=2026-01-17T23:59:59Z&agg=avg
```

### 事件列表
```http
GET /api/events?limit=200
```

---

## 📝 更新日志

### v1.0.0 (2026-01-17)
- 初始版本
- 支持 CPU/磁盘/GPU 监控
- 支持 systemd 服务状态监控
- 前端 Dashboard
- 5s 实时刷新 + 小时级历史数据
