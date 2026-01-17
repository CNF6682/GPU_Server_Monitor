# Monitor Agent

Linux 服务器监控代理，提供 HTTP 接口供中心节点拉取系统指标数据。

## 功能特性

- ✅ CPU 使用率采集（基于 /proc/stat）
- ✅ 磁盘使用情况采集（支持多挂载点）
- ✅ GPU 使用率和显存采集（NVIDIA）
- ✅ systemd 服务状态监控
- ✅ 健康检查端点
- ✅ 服务发现功能
- ✅ Token 认证保护
- ✅ 异步并发采集
- ✅ 资源占用低（< 100MB 内存）

## 系统要求

- Python 3.8+
- Linux 操作系统
- systemd（用于服务监控）
- NVIDIA 驱动（可选，用于 GPU 监控）

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv /opt/monitor-agent/venv

# 激活虚拟环境
source /opt/monitor-agent/venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

复制配置文件模板并修改：

```bash
sudo mkdir -p /etc/monitor-agent
sudo cp config.example.yaml /etc/monitor-agent/config.yaml
sudo nano /etc/monitor-agent/config.yaml
```

配置示例：

```yaml
node_id: "srv-01"
listen: "0.0.0.0:9109"
token: "your-random-token-here"
disks:
  - "/"
services_allowlist: []
gpu: "auto"
```

生成随机 Token：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. 运行

#### 方式 1：直接运行（开发测试）

```bash
python -m monitor_agent
```

#### 方式 2：使用 systemd（生产环境）

创建 systemd 服务文件 `/etc/systemd/system/monitor-agent.service`：

```ini
[Unit]
Description=Monitor Agent
After=network.target

[Service]
User=monitor-agent
Group=monitor-agent
Restart=always
RestartSec=2
Environment=MONITOR_AGENT_CONFIG=/etc/monitor-agent/config.yaml
ExecStart=/opt/monitor-agent/venv/bin/python -m monitor_agent

# 资源限制
MemoryLimit=100M
CPUQuota=5%

# 健康检查
ExecStartPost=/bin/sleep 2
ExecStartPost=/usr/bin/curl -f http://127.0.0.1:9109/v1/health

# 优雅停止
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now monitor-agent
sudo systemctl status monitor-agent
```

## API 接口

### 1. 健康检查

```bash
GET /v1/health
```

无需认证，返回各采集器的健康状态。

### 2. 获取快照

```bash
GET /v1/snapshot
Authorization: Bearer <token>
```

返回系统当前状态快照（CPU、磁盘、GPU、服务）。

### 3. 服务发现

```bash
GET /v1/services
Authorization: Bearer <token>
```

返回所有可用的 systemd 服务列表。

## 测试

运行测试脚本：

```bash
python test_agent.py localhost 9109 your-token
```

## 故障排查

### Agent 无响应

1. 检查服务状态：`sudo systemctl status monitor-agent`
2. 查看日志：`sudo journalctl -u monitor-agent -n 50`
3. 测试端口：`curl http://localhost:9109/v1/health`

### GPU 采集失败

1. 验证驱动：`nvidia-smi`
2. 检查权限：确保 monitor-agent 用户可执行 nvidia-smi
3. 临时禁用：配置文件设置 `gpu: off`

## 开发

### 项目结构

```
monitor_agent/
├── __init__.py          # 包初始化
├── __main__.py          # 主程序入口
├── app.py               # FastAPI 应用
├── config.py            # 配置管理
├── models.py            # 数据模型
├── utils.py             # 工具函数
└── collectors/          # 采集器模块
    ├── __init__.py
    ├── cpu.py           # CPU 采集
    ├── disk.py          # 磁盘采集
    ├── gpu.py           # GPU 采集
    └── systemd.py       # systemd 采集
```

## 许可证

MIT License
