# 服务器状态监控方案（LAN / Linux 节点 / 5s 刷新 / 每小时入库 / 保留 30 天）

适用场景：3 台 Linux 服务器在同一校园网（同一内网可互通），GPU 均为 NVIDIA；中心节点为 Windows（本仓库所在机器）；需要持续监控并在前端展示；监控范围以“在线/服务状态 + CPU/磁盘/GPU 占用”为主；前端 5 秒刷新；历史数据保留 30 天，但仅每小时保存 1 条历史点；仅内网自用；暂不做通知告警。

---

## 1. 目标与边界

### 目标（MVP）
- 以 **5s 间隔**获取每台服务器“当前状态”（用于在线判断与前端刷新），但**不把每次结果都写入历史库**：
  - 在线状态（last_seen/心跳）
  - CPU 使用率（%）
  - 磁盘使用（% + bytes）
  - GPU 使用率（%）与显存占用（可选，NVIDIA 场景）
- （可选）服务状态（systemd unit：active/inactive/failed），默认不配置则不采集
- 前端每 **5s 刷新**（轮询），提供概览页与单机详情页。
- 历史入库：每台服务器 **每小时保存 1 条**（建议按整点写入一条“快照/聚合”）。
- 历史数据保留 **30 天**，到期自动清理。
- 支持在**前端界面动态添加/删除服务器**（中心节点维护服务器清单与采集配置，无需改代码/重启即可生效）。

### 非目标（后续再做）
- 外网访问、复杂鉴权、多租户权限
- 通知告警（短信/邮件/IM）
- 日志采集、分布式追踪、自动化修复

---

## 2. 总体架构（推荐：Agent + 中心汇聚 Pull）

选择 **Pull**（中心节点主动拉取）原因：
- 同一内网可直连，无 NAT 穿透需求；
- 中心统一掌控采集频率、超时、重试、退避；
- agent 更轻量，不需要维护上报队列。

```
┌────────────────────────校园网/LAN────────────────────────┐
│                                                          │
│  ┌──────────────┐      HTTP(S)+Token       ┌───────────┐ │
│  │ Linux Server A│<------------------------│           │ │
│  │ monitor-agent │                         │           │ │
│  └──────────────┘                         ┌│ monitor-  │ │
│                                            │ aggregator│ │
│  ┌──────────────┐      HTTP(S)+Token       │ (API+DB)  │ │
│  │ Linux Server B│<------------------------│           │ │
│  │ monitor-agent │                         └───────────┘ │
│  └──────────────┘                                 │       │
│                                                    │HTTP   │
│                                              ┌───────────┐ │
│                                              │ Frontend   │ │
│                                              │ dashboard  │ │
│                                              └───────────┘ │
└──────────────────────────────────────────────────────────┘
```

组件说明：
- **monitor-agent（每台 Linux 一份）**：提供一个本地 HTTP 接口，返回“当前快照”（CPU/磁盘/GPU/服务状态）。
- **monitor-aggregator（中心节点一份）**：每 5s 拉取所有 agent，写入 SQLite（或 Postgres），对外提供 API 给前端。
- **dashboard 前端**：用现成模板做 UI；通过 API 拉取数据，5s 轮询刷新。

---

## 3. 数据采集口径（必须明确，否则图表会“漂移”）

### 3.1 在线状态（Alive/Last seen）
- 判定：中心节点拉取成功即认为在线，并更新 `last_seen_at`。
- 离线阈值：`now - last_seen_at > 2 * interval + timeout` 视为离线（例：interval=5s，timeout=2s，则阈值≈12s）。

### 3.2 CPU 使用率
推荐口径：**全机总 CPU 利用率**（0~100%）
- agent 端通过 `/proc/stat` 两次采样的 delta 计算（或用 `psutil.cpu_percent(interval=None)` 这种基于上一周期的口径）。
- 注意：如果 agent 仅返回“瞬时值”，中心无法复算；因此建议 agent 自己维护上一周期，返回已算好的 `cpu_pct`。

### 3.3 磁盘使用率
至少定义清楚“监控哪些挂载点”：
- 默认：`/`（根分区）
- 可选：`/data`、`/var/lib/docker` 等业务盘

建议返回：
- `disk_used_pct`（0~100）
- `disk_used_bytes`、`disk_total_bytes`

### 3.4 GPU 使用率（NVIDIA）
建议先只支持 NVIDIA（后续再扩 AMD/Intel）：
- 获取方式：`nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits`
- 多 GPU：
  - MVP：取 `max(utilization.gpu)` + `sum(memory.used/total)` 或返回数组并由中心聚合。

### 3.5 服务状态（systemd）
由 agent 读取配置中的 unit 列表，例如：`nginx.service`、`docker.service`、`myapp.service`。
- 状态字段建议：`active_state`（active/inactive/failed）+ `sub_state`（running/exited/dead…）
- 可附带 `since`（状态变更时间）作为后续事件判断依据。

---

## 4. 数据模型（中心节点）

### 4.1 数据量估算（按“每小时入库”）
30 天、每小时 1 条：
- 每台服务器样本数：`30 * 24 = 720`
- 3 台服务器：`2160` 行级别（非常轻量，SQLite 足够）

注意：仍然会有“5s 拉取”用于在线与前端刷新，但这部分建议只放在内存/缓存表中，不作为 30 天历史数据。

### 4.1.1 数据流转图

```
┌─────────────────────┐
│   5s 采集循环        │  每 5 秒拉取所有 agent
└──────────┬──────────┘
           │
           ├─→ server_latest (内存 dict / Redis)
           │    └─→ GET /api/servers (前端 5s 刷新)
           │
           └─→ hourly_buffer (内存列表)
                   │  每小时 720 个采样点（3 台 × 240 次/小时）
                   ▼
            ┌──────────────┐
            │ 整点聚合任务  │  计算 avg/max/min
            └──────┬───────┘
                   │
                   └─→ samples_hourly (SQLite)
                        └─→ GET /api/servers/{id}/timeseries (历史图表)
```

### 4.1.2 小时聚合实现逻辑

**核心思路**：内存缓冲区收集 5s 采样数据，整点触发聚合计算并入库。

**实现伪代码**（Python）：

```python
from collections import defaultdict
from datetime import datetime, timedelta
import asyncio

# 全局状态
server_latest = {}  # {server_id: {ts, online, cpu_pct, ...}}
hourly_buffer = defaultdict(list)  # {server_id: [snapshot1, snapshot2, ...]}

async def collect_loop():
    """每 5s 拉取所有 agent"""
    while True:
        for server in get_enabled_servers():
            try:
                snapshot = await fetch_agent_snapshot(server)
                # 1. 更新实时状态（用于前端 5s 刷新）
                server_latest[server.id] = {
                    "ts": snapshot["ts"],
                    "online": True,
                    "cpu_pct": snapshot["cpu_pct"],
                    "disk_used_pct": snapshot["disks"][0]["used_pct"],
                    "gpu_util_pct": snapshot["gpus"][0]["util_pct"] if snapshot["gpus"] else None,
                    # ...
                }
                # 2. 追加到小时缓冲区（用于整点聚合）
                hourly_buffer[server.id].append({
                    "ts": snapshot["ts"],
                    "cpu_pct": snapshot["cpu_pct"],
                    "gpu_util_pct": snapshot["gpus"][0]["util_pct"] if snapshot["gpus"] else None,
                    # ...
                })
            except Exception as e:
                # 拉取失败 → 标记离线
                if server.id in server_latest:
                    server_latest[server.id]["online"] = False
        await asyncio.sleep(5)

async def hourly_aggregation():
    """每小时整点执行聚合"""
    while True:
        # 等到下一个整点
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        await asyncio.sleep((next_hour - now).total_seconds())
        
        # 对每台服务器的缓冲数据做聚合
        for server_id, snapshots in hourly_buffer.items():
            if not snapshots:
                continue
            
            # 计算聚合指标
            cpu_values = [s["cpu_pct"] for s in snapshots if s["cpu_pct"] is not None]
            gpu_values = [s["gpu_util_pct"] for s in snapshots if s.get("gpu_util_pct") is not None]
            
            cpu_avg = sum(cpu_values) / len(cpu_values) if cpu_values else None
            cpu_max = max(cpu_values) if cpu_values else None
            gpu_avg = sum(gpu_values) / len(gpu_values) if gpu_values else None
            gpu_max = max(gpu_values) if gpu_values else None
            
            # 磁盘取最后一个快照值（变化慢）
            last_snapshot = snapshots[-1]
            
            # 写入数据库
            save_hourly_sample(
                server_id=server_id,
                ts=next_hour.strftime("%Y-%m-%d %H:00:00"),
                cpu_pct_avg=cpu_avg,
                cpu_pct_max=cpu_max,
                disk_used_pct=last_snapshot.get("disk_used_pct"),
                gpu_util_pct_avg=gpu_avg,
                gpu_util_pct_max=gpu_max,
                # ...
            )
        
        # 清空缓冲区
        hourly_buffer.clear()
```

**关键点**：
- **缓冲区容量**：3 台 × 240 次/小时 = 720 条/小时（内存占用 < 1MB）
- **容错**：Agent 拉取失败时跳过该次采样，聚合时基于实际收集到的数据计算
- **时间对齐**：整点聚合任务在下一个整点触发（如 10:00:00 触发时聚合 09:00~10:00 的数据）

### 4.2 建议表结构（SQLite / Postgres 均可）

`servers`
- `id` (pk)
- `name`
- `host`（IP/域名）
- `agent_port`
- `enabled`
- `services`（JSON 数组，可选：该服务器需要监控的 systemd units；为空表示不监控服务状态）
- `token`（用于拉取该服务器 agent；建议每台不同）
- `last_seen_at`
- `created_at`

`samples_hourly`（核心历史时序表：每小时 1 条，**存储聚合值**）
- `server_id` (idx)
- `ts` (idx，整点时间戳，如 "2026-01-17 10:00:00")
- `cpu_pct_avg`（过去 1 小时平均 CPU 使用率）
- `cpu_pct_max`（过去 1 小时峰值 CPU 使用率）
- `disk_used_pct`（整点快照值，磁盘变化慢，取快照即可）
- `disk_used_bytes`（整点快照值）
- `disk_total_bytes`（整点快照值）
- `gpu_util_pct_avg`（nullable，过去 1 小时平均 GPU 使用率）
- `gpu_util_pct_max`（nullable，过去 1 小时峰值 GPU 使用率）
- `gpu_mem_used_mb`（nullable，整点快照值）
- `gpu_mem_total_mb`（nullable，整点快照值）
- **聚合说明**：CPU/GPU 用 avg + max（反映"平均负载"与"尖峰"），磁盘用快照值（变化慢且无需聚合）

`service_status`
- 说明：仅当 `servers.services` 非空时才写入（否则不产生该表数据）
- `server_id` (idx)
- `ts` (idx)
- `unit_name`
- `active_state`
- `sub_state`

`events`（状态变化事件，便于前端展示“什么时候掉线/恢复”）
- `server_id` (idx)
- `ts` (idx)
- `type`（server_down/server_up/service_failed/service_recovered…）
- `message`

`server_latest`（最新状态缓存：用于 5s 刷新，**推荐纯内存实现**）
- **实现方式**：Python `dict` / Node.js `Map` / Redis Hash（可选）
- **数据结构示例**（Python）：
  ```python
  server_latest = {
      1: {  # server_id
          "ts": "2026-01-17T19:30:00Z",
          "online": True,
          "cpu_pct": 23.4,
          "disk_used_pct": 67.2,
          "disk_used_bytes": 123456789,
          "disk_total_bytes": 184467440737,
          "gpu_util_pct": 85.0,
          "gpu_mem_used_mb": 6144,
          "gpu_mem_total_mb": 8192,
          "services_failed_count": 0
      }
  }
  ```
- **持久化**：无需持久化（重启后 5s 内自动恢复）
- **并发安全**：单线程或用 `asyncio.Lock()` 保护写入

### 4.3 保留策略（30 天）
每天跑一次清理任务：
- 删除 `ts < now - 30d` 的 `samples_hourly` / `service_status` / `events`
- SQLite 建议定期 `VACUUM`（可每周/每月一次，避免频繁）

---

## 5. API 设计（给前端用）

5 秒刷新不要求推送，API 走 HTTP 即可。

### 5.1 概览
- `GET /api/servers`
  - 返回：每台服务器 `name/online/last_seen_at` + 最新一条样本（CPU/磁盘/GPU）+ 服务健康摘要（failed 个数）
  - **返回格式示例**：
    ```json
    [
      {
        "id": 1,
        "name": "srv-01",
        "host": "10.0.0.101",
        "agent_port": 9109,
        "enabled": true,
        "online": true,
        "last_seen_at": "2026-01-17T19:35:00Z",
        "latest": {
          "ts": "2026-01-17T19:35:00Z",
          "cpu_pct": 23.4,
          "disk_used_pct": 67.2,
          "disk_used_bytes": 123456789,
          "disk_total_bytes": 184467440737,
          "gpu_util_pct": 85.0,
          "gpu_mem_used_mb": 6144,
          "gpu_mem_total_mb": 8192,
          "services_failed_count": 0
        }
      },
      {
        "id": 2,
        "name": "srv-02",
        "host": "10.0.0.102",
        "agent_port": 9109,
        "enabled": true,
        "online": false,
        "last_seen_at": "2026-01-17T19:30:12Z",
        "latest": null
      }
    ]
    ```

### 5.1.1 服务器管理（前端 CRUD）
用于“动态添加/删除服务器”。建议仅在内网开放，并对该组接口加一个简单的管理口令（例如 `X-Admin-Token`）。
- `POST /api/servers`
  - body：`name, host, agent_port, token, services[], enabled`
  - 行为：写入 `servers`，立即纳入下一轮 5s 拉取
- `PUT /api/servers/{id}`
  - body：同上（可部分字段）
  - 行为：更新采集配置（例如修改 services 列表、端口、token）
- `DELETE /api/servers/{id}`
  - 行为：从 `servers` 删除或软删除（推荐 `enabled=false`）

### 5.2 单机详情
- `GET /api/servers/{id}`
  - 返回：基础信息 + 最近一次采集快照
- `GET /api/servers/{id}/timeseries?metric=cpu_pct&from=...&to=...&agg=avg`
  - 参数说明：
    - `metric`：指标名称（`cpu_pct`/`disk_used_pct`/`gpu_util_pct`）
    - `from`/`to`：时间范围（ISO 8601 格式）
    - `agg`：聚合类型（`avg`/`max`），默认 `avg`
  - 返回：小时粒度时序数据（每个数据点代表 1 小时）
  - **返回格式示例**：
    ```json
    {
      "server_id": 1,
      "metric": "cpu_pct",
      "agg": "avg",
      "data": [
        {"ts": "2026-01-17T10:00:00Z", "value": 23.4},
        {"ts": "2026-01-17T11:00:00Z", "value": 45.2},
        {"ts": "2026-01-17T12:00:00Z", "value": 38.7}
      ]
    }
    ```
  - **注意**：历史数据仅支持小时粒度，前端查询 24 小时返回 24 个点，查询 7 天返回 168 个点
- `GET /api/servers/{id}/services?at=latest`
  - 返回：最新服务状态列表；若该服务器 `services[]` 为空，返回空数组

### 5.2.1 服务发现（可选，用于“我也不知道要监控哪些服务”的场景）
MVP 推荐做一个“先发现、再勾选”的流程，避免默认硬编码一堆服务导致噪声。
- `GET /api/servers/{id}/services/catalog`
  - 行为：中心节点调用该服务器 agent 的服务发现端点，返回可选服务列表（建议返回 running/enabled 的 service）
  - 用途：前端展示勾选框，用户选择 2~5 个“关键服务”保存到 `servers.services`

### 5.3 事件
- `GET /api/events?limit=200`

---

## 6. Agent 接口（中心节点拉取协议）

### 6.1 HTTP 端点

#### 6.1.1 主要数据端点
- `GET /v1/snapshot`
  - Header：`Authorization: Bearer <token>`
  - 行为：返回 CPU/磁盘/GPU 等快照；仅当请求中带 `services` 或 agent 配置了默认服务清单时，才返回 `services[]`
  - 返回 JSON（示例）：

```json
{
  "node_id": "srv-a",
  "ts": "2026-01-17T10:00:00Z",
  "cpu_pct": 23.4,
  "disks": [
    { "mount": "/", "used_bytes": 123, "total_bytes": 456, "used_pct": 27.0 }
  ],
  "gpus": [
    { "index": 0, "util_pct": 56, "mem_used_mb": 2048, "mem_total_mb": 8192 }
  ],
  "services": [
    { "name": "nginx.service", "active_state": "active", "sub_state": "running" }
  ]
}
```

#### 6.1.2 健康检查端点
- `GET /v1/health`
  - Header：可选（建议不强制 token，方便 systemd 和中心节点快速检测）
  - 返回：agent 自身健康状态
  - **返回格式示例**：
    ```json
    {
      "status": "ok",
      "timestamp": "2026-01-17T19:35:00Z",
      "checks": {
        "cpu": "ok",
        "disk": "ok",
        "gpu": "ok",
        "systemd": "ok"
      },
      "details": {
        "cpu": null,
        "disk": null,
        "gpu": "NVIDIA driver available, 1 GPU detected",
        "systemd": null
      }
    }
    ```
  - **状态码**：`ok` / `degraded`（部分功能异常，如 GPU 不可用）/ `error`（严重错误）
  - **用途**：
    - systemd `ExecStartPost` 验证启动成功
    - 中心节点区分"离线"vs"在线但功能降级"
    - 运维巡检脚本快速检测

#### 6.1.3 服务发现端点（可选）
- `GET /v1/services`
  - Header：`Authorization: Bearer <token>`
  - 返回：可供勾选的 service 列表（建议以 running/enabled 为主，并附带简要状态）
  - 用途：前端“发现服务”按钮调用（经由中心节点转发或中心节点代调用）

### 6.2 Agent 配置（示例）
建议每台机器一个 `/etc/monitor-agent/config.yaml`：
- `node_id`: 唯一标识（用于数据归属）
- `listen`: `0.0.0.0:9109`（端口可自定义）
- `token`: 与中心共享的 token
- `disks`: 需要监控的挂载点列表（`/`, `/data`…）
- `services_allowlist`: （可选）允许被查询的 systemd unit 列表；为空表示不开放服务查询（仅开放资源指标）
- `gpu`: `auto|off|nvidia`

---

## 7. 部署与运维（建议流程）

### 7.1 每台 Linux：安装与配置 monitor-agent（systemd，具体步骤）
下面给出一套“可复制”的通用步骤（以 Ubuntu/Debian 风格为主；RHEL/CentOS 仅包管理器不同）。

#### A) 准备一个专用用户与目录
1. 创建用户（无登录 shell 也可以）：
   - `sudo useradd --system --no-create-home --shell /usr/sbin/nologin monitor-agent || true`
2. 创建目录：
   - `sudo mkdir -p /opt/monitor-agent /etc/monitor-agent`
   - `sudo chown -R root:root /opt/monitor-agent /etc/monitor-agent`

#### B) 安装运行时（两种任选其一）
- 方案 1（推荐实现简单）：Python + venv
  1. 安装依赖：`sudo apt-get update && sudo apt-get install -y python3 python3-venv`
  2. 创建 venv：`sudo python3 -m venv /opt/monitor-agent/venv`
  3. 安装依赖包（示例：FastAPI + psutil + PyYAML）：  
     `sudo /opt/monitor-agent/venv/bin/pip install --upgrade pip`  
     `sudo /opt/monitor-agent/venv/bin/pip install fastapi uvicorn psutil pyyaml`
  4. NVIDIA 采集依赖：确保已安装驱动并可执行 `nvidia-smi`（一般在 `/usr/bin/nvidia-smi`）。
- 方案 2：Go 静态单文件（二进制分发最省事）
  - 直接放置 agent 二进制到 `/opt/monitor-agent/monitor-agent` 并赋可执行权限。

#### C) 写配置文件（每台机器都需要一份）
说明：是的，**每台机器都需要一个配置**，但内容很少，主要是 `node_id`、监听端口、token、要监控的挂载点和 systemd 服务列表。

1. 编辑 `/etc/monitor-agent/config.yaml`：

```yaml
node_id: "srv-01"
listen: "0.0.0.0:9109"
token: "REPLACE_WITH_RANDOM_TOKEN"
disks:
  - "/"
services_allowlist: []
gpu: "nvidia"
```

2. 生成 token 建议用随机串（每台可不同，也可统一；内网自用建议每台不同更安全）：
   - `python3 - <<'PY'\nimport secrets; print(secrets.token_urlsafe(32))\nPY`

#### D) 配置防火墙（仅允许 Windows 中心节点访问）
假设中心节点 IP 为 `10.0.0.10`，agent 端口为 `9109`：
- `ufw`（Ubuntu 常见）：
  - `sudo ufw allow from 10.0.0.10 to any port 9109 proto tcp`
- `firewalld`（RHEL 常见）：
  - `sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=10.0.0.10 port port=9109 protocol=tcp accept'`
  - `sudo firewall-cmd --reload`

#### E) 创建 systemd 服务并启动
1. 创建 `/etc/systemd/system/monitor-agent.service`：

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

# 资源限制（防止 agent 自身占用过多）
MemoryLimit=100M
CPUQuota=5%

# 健康检查（启动后验证服务可用）
ExecStartPost=/bin/sleep 2
ExecStartPost=/usr/bin/curl -f http://127.0.0.1:9109/v1/health

# 优雅停止
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
```

2. 启动并开机自启：
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable --now monitor-agent`
   - `sudo systemctl status monitor-agent --no-pager`

#### F) 从中心节点做连通性检查
在 Windows 中心节点 PowerShell：
- `curl.exe -H "Authorization: Bearer <token>" http://<linux-ip>:9109/v1/snapshot`

> 备注：上面 `monitor_agent`/`python -m monitor_agent` 是一个占位模块名；你如果要我继续落地实现，我会在仓库里提供 agent 源码与安装方式，并同步改这里为真实命令。

### 7.2 Windows 中心节点：部署 monitor-aggregator + 前端（具体步骤）
中心节点职责（按新口径）：
- 每 5s 拉取所有 agent，更新 `server_latest` 与 `last_seen_at`（供前端 5s 刷新）
- 每小时（整点）将“最新状态”写入 `samples_hourly`（供 30 天历史）
- 状态变化写 `events`（掉线/恢复、服务从 active->failed 等）
- 每天清理 30 天前历史数据

推荐落地方式（与你现有框架最贴合）：
1. `monitor-aggregator` 作为一个常驻进程（例如 Python/Node/Go）
2. 用本仓库的 NSSM 框架托管：
   - 新增 `services/monitor-aggregator/service.json`
   - `exe` 指向 `python.exe` 或 `node.exe` 或编译后的可执行文件
   - `workDir` 指向仓库目录
   - `stdout/stderr` 输出到 `logs/monitor-aggregator/*`
3. 前端静态资源：
   - MVP 可以由 aggregator 直接托管静态文件（`/`），同域访问 `/api/*`
   - 或者单独跑一个静态服务器进程，同样用 NSSM 托管

Windows 侧配置文件建议放置：
- `ops/monitor/config.yaml`（包含三台 Linux 的 IP、端口、token、node_id 映射）
- SQLite 数据库：`ops/monitor/data/monitor.db`

### 7.2.1 数据库初始化

创建 `ops/monitor/schema.sql`：

```sql
-- 服务器配置表
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    host TEXT NOT NULL,
    agent_port INTEGER DEFAULT 9109,
    enabled INTEGER DEFAULT 1,
    services TEXT,  -- JSON 数组
    token TEXT NOT NULL,
    last_seen_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 小时聚合历史数据表
CREATE TABLE IF NOT EXISTS samples_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    cpu_pct_avg REAL,
    cpu_pct_max REAL,
    disk_used_pct REAL,
    disk_used_bytes INTEGER,
    disk_total_bytes INTEGER,
    gpu_util_pct_avg REAL,
    gpu_util_pct_max REAL,
    gpu_mem_used_mb INTEGER,
    gpu_mem_total_mb INTEGER,
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_samples_hourly_server_ts ON samples_hourly(server_id, ts DESC);

-- 服务状态表
CREATE TABLE IF NOT EXISTS service_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    unit_name TEXT NOT NULL,
    active_state TEXT,
    sub_state TEXT,
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_service_status_server_ts ON service_status(server_id, ts DESC);

-- 事件表
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    message TEXT,
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);

-- 配置 WAL 模式（写不阻塞读）
PRAGMA journal_mode=WAL;
```

初始化命令（PowerShell）：
```powershell
sqlite3.exe ops\monitor\data\monitor.db < ops\monitor\schema.sql
```

### 7.2.2 事件检测逻辑

**核心思路**：在每次采集循环中，通过比较当前状态与上一次状态，检测变化并写入 `events` 表。

**实现伪代码**（Python）：

```python
# 全局状态缓存
prev_state = {}  # {server_id: {"online": bool, "services": {unit_name: active_state}}}

async def detect_and_save_events(server_id, current_online, current_services):
    """检测状态变化并保存事件"""
    events = []
    prev = prev_state.get(server_id, {})
    
    # 1. 在线状态变化
    prev_online = prev.get("online", None)
    if prev_online is True and current_online is False:
        events.append({
            "type": "server_down",
            "message": "Server went offline"
        })
    elif prev_online is False and current_online is True:
        events.append({
            "type": "server_up",
            "message": "Server came back online"
        })
    
    # 2. 服务状态变化（仅当配置了服务监控时）
    if current_services:
        prev_services = prev.get("services", {})
        for svc in current_services:
            unit_name = svc["name"]
            current_active = svc["active_state"]
            prev_active = prev_services.get(unit_name)
            
            if prev_active == "active" and current_active == "failed":
                events.append({
                    "type": "service_failed",
                    "message": f"Service {unit_name} failed"
                })
            elif prev_active == "failed" and current_active == "active":
                events.append({
                    "type": "service_recovered",
                    "message": f"Service {unit_name} recovered"
                })
    
    # 3. 保存事件到数据库
    for event in events:
        save_event(server_id, event["type"], event["message"])
    
    # 4. 更新状态缓存
    prev_state[server_id] = {
        "online": current_online,
        "services": {s["name"]: s["active_state"] for s in (current_services or [])}
    }

# 在采集循环中调用
async def collect_loop():
    while True:
        for server in get_enabled_servers():
            try:
                snapshot = await fetch_agent_snapshot(server)
                online = True
                services = snapshot.get("services", [])
                # ... 更新 server_latest ...
            except Exception as e:
                online = False
                services = []
            
            # 检测事件
            await detect_and_save_events(server.id, online, services)
        
        await asyncio.sleep(5)
```

**事件类型定义**：
- `server_down`：服务器从在线变为离线
- `server_up`：服务器从离线恢复在线
- `service_failed`：服务从 active 变为 failed
- `service_recovered`：服务从 failed 恢复为 active

---

## 8. 前端（模板选型与页面规划）

你希望使用现成模板，推荐优先考虑（易改、组件齐全）：
- 本项目推荐（默认采用）：`tabler/tabler`：https://github.com/tabler/tabler
  - 原因：纯 HTML/JS/CSS，dashboard/表格/表单组件齐全；可直接由 aggregator 托管静态资源，部署最省事
- 可选（更“企业后台”风格，二次开发成本更高）：`ant-design/ant-design-pro`

页面建议（MVP）：
- **Overview**：服务器列表（在线/离线）、CPU/磁盘/GPU 最新值、服务异常数
- **Server Detail**：CPU/磁盘/GPU 近 1h/24h 曲线；服务列表（active/failed）
- **Events**：最近掉线/恢复、服务失败/恢复
- **Servers (Manage)**：动态添加/删除/编辑服务器（host/port/token/services/enabled）
  - 在编辑页提供“发现服务（Discover）”按钮：调用 `/api/servers/{id}/services/catalog` 拉取候选列表，勾选后保存到 `services[]`

前端交互约定（MVP）：
- 刷新：`GET /api/servers` 每 5s 轮询
- 新增服务器：
  1) 你先在该 Linux 上完成 agent 安装与 token 设置（`/etc/monitor-agent/config.yaml`）
  2) 在前端 “Servers (Manage)” 填入 `host/port/token/services`
  3) 保存后中心节点下一轮拉取即生效
 - 不确定要监控哪些服务：
   1) 先保持 `services[]` 为空（不监控服务）
   2) 需要时在编辑页点 “发现服务”，从候选列表勾选少量关键项再保存

---

## 9. 风险点与提前约定

- **5s 拉取但每小时入库**：历史图表只有小时粒度；若后续想看更细（分钟级/秒级），需调整入库策略或引入 TSDB。
- **GPU 采集依赖**：无 NVIDIA 或无 `nvidia-smi` 时必须优雅降级（字段为空即可）。
- **服务口径**：systemd unit 名称必须统一（建议写到每台 agent 的配置里，不要在中心硬编码）。
- **时间同步**：建议所有 Linux 节点启用 NTP；同时以中心入库时间为准更稳定。

---

## 10. SSH 备选方案（不推荐，但可用）

如果你明确不想在 Linux 上部署 agent，也可以让中心节点通过 SSH 定时执行命令抓取数据：
- CPU/磁盘：远端执行 `cat /proc/stat`、`df -P /` 等
- GPU：远端执行 `nvidia-smi --query-gpu=...`
- 服务：远端执行 `systemctl is-active <unit>`

但有明显代价：
- 需要分发 SSH key/账号权限（安全面更大）
- 并发与超时处理更复杂（容易卡住）
- 命令输出解析更脆弱（不同发行版/语言环境差异）

因此本方案仍以 agent 为主，SSH 仅作为临时过渡。

---

## 11. 故障排查手册

### 11.1 Agent 相关问题

#### 问题：Agent 无响应
**症状**：中心节点无法拉取数据，服务器显示离线

**排查步骤**：
1. 检查 systemd 状态：
   ```bash
   sudo systemctl status monitor-agent
   ```
2. 查看最近日志：
   ```bash
   sudo journalctl -u monitor-agent -n 50 --no-pager
   ```
3. 测试端口监听：
   ```bash
   curl http://localhost:9109/v1/health
   ```
4. 检查防火墙规则：
   ```bash
   sudo ufw status | grep 9109
   ```
5. 手动测试采集（如 CPU/GPU）：
   ```bash
   # CPU
   cat /proc/stat
   # GPU
   nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits
   ```

**常见原因**：
- 端口被占用：`sudo lsof -i :9109`
- Token 不匹配：检查配置文件与中心节点配置
- GPU 驱动问题：验证 `nvidia-smi` 可执行
- 权限不足：确保 `monitor-agent` 用户有必要权限

#### 问题：Agent 启动失败
**症状**：`systemctl start monitor-agent` 失败

**排查步骤**：
1. 查看详细错误：
   ```bash
   sudo systemctl status monitor-agent -l
   ```
2. 检查配置文件语法：
   ```bash
   cat /etc/monitor-agent/config.yaml
   ```
3. 测试 Python 环境：
   ```bash
   /opt/monitor-agent/venv/bin/python --version
   /opt/monitor-agent/venv/bin/pip list
   ```
4. 手动运行（调试模式）：
   ```bash
   sudo -u monitor-agent /opt/monitor-agent/venv/bin/python -m monitor_agent
   ```

#### 问题：GPU 数据采集失败但其他正常
**症状**：健康检查显示 `gpu: degraded`

**解决方案**：
- 验证 NVIDIA 驱动：`nvidia-smi`
- 检查权限：`monitor-agent` 用户能否执行 `nvidia-smi`
- 配置文件设置 `gpu: off` 禁用 GPU 监控（临时方案）

---

### 11.2 中心节点问题

#### 问题：拉取失败（网络/超时）
**症状**：某台服务器持续显示离线，但 ping 通

**排查步骤**：
1. 从中心节点测试连接：
   ```powershell
   # Windows PowerShell
   Test-NetConnection -ComputerName 10.0.0.101 -Port 9109
   ```
2. 手动拉取测试：
   ```powershell
   curl.exe -H "Authorization: Bearer <token>" http://10.0.0.101:9109/v1/snapshot
   ```
3. 检查防火墙（Linux 端）：
   ```bash
   sudo ufw status verbose
   ```
4. 检查 Token 是否正确：对比 `ops/monitor/config.yaml` 与 agent 配置

**常见原因**：
- 防火墙未放行中心节点 IP
- Token 不匹配或过期
- Agent 端口配置错误

#### 问题：数据库锁/写入慢
**症状**：API 响应慢，日志显示数据库锁

**排查步骤**：
1. 检查 WAL 模式：
   ```powershell
   sqlite3.exe ops\monitor\data\monitor.db "PRAGMA journal_mode;"
   # 应返回 "wal"
   ```
2. 检查数据库大小：
   ```powershell
   dir ops\monitor\data\monitor.db
   ```
3. 完整性检查：
   ```powershell
   sqlite3.exe ops\monitor\data\monitor.db "PRAGMA integrity_check;"
   ```

**解决方案**：
- 启用 WAL 模式（如果未启用）：
  ```sql
  PRAGMA journal_mode=WAL;
  ```
- 定期 VACUUM（每月一次）：
  ```powershell
  sqlite3.exe ops\monitor\data\monitor.db "VACUUM;"
  ```
- 考虑迁移到 PostgreSQL（如数据量大于 1GB）

#### 问题：内存占用过高
**症状**：aggregator 进程占用内存持续增长

**排查步骤**：
1. 检查 `hourly_buffer` 大小（是否正常清理）
2. 检查 `server_latest` 是否泄漏（服务器删除后未清理）
3. 查看是否有异常大的响应数据（如 GPU 数组过大）

**解决方案**：
- 在整点聚合后确保 `hourly_buffer.clear()`
- 服务器删除时清理对应缓存
- 添加内存监控，设置重启策略（如每天凌晨重启）

---

### 11.3 前端问题

#### 问题：数据不刷新
**症状**：前端显示的数据一直不变

**排查步骤**：
1. 打开浏览器开发者工具 → Network
2. 检查是否持续发送 `/api/servers` 请求（每 5s）
3. 检查响应状态码（应为 200）
4. 检查响应内容中的 `ts` 时间戳是否更新

**常见原因**：
- 浏览器缓存：强制刷新（Ctrl+F5）
- API 端点错误：检查前端配置的 API 地址
- CORS 问题：检查 aggregator 是否允许跨域

#### 问题：历史图表无数据
**症状**：概览页有数据，但详情页图表为空

**排查步骤**：
1. 检查是否有历史数据：
   ```sql
   SELECT COUNT(*) FROM samples_hourly WHERE server_id = 1;
   ```
2. 检查时间范围查询：
   ```powershell
   curl.exe "http://localhost:8080/api/servers/1/timeseries?metric=cpu_pct&from=2026-01-16T00:00:00Z&to=2026-01-17T23:59:59Z&agg=avg"
   ```
3. 验证聚合任务是否执行（查看日志）

**常见原因**：
- 小时聚合任务未启动
- 查询时间范围没有数据（需等待至少 1 小时后才有历史数据）
- 前端图表组件配置错误

---

### 11.4 数据一致性问题

#### 问题：服务器状态显示"在线"但数据为空
**症状**：`online: true` 但 `latest: null`

**原因**：
- `last_seen_at` 更新了，但 `server_latest` 内存缓存未写入
- Agent 返回了 HTTP 200 但 JSON 格式错误

**解决方案**：
- 检查 agent 返回的 JSON 格式是否完整
- 增加异常处理，解析失败时标记离线

#### 问题：事件重复触发
**症状**：同一个"掉线"事件重复出现多次

**原因**：
- `prev_state` 缓存未正确更新
- 重启 aggregator 导致状态丢失

**解决方案**：
- 确保每次检测后更新 `prev_state`
- 添加事件去重逻辑（同一服务器同一类型事件 1 分钟内只记录一次）

---

### 11.5 性能优化建议

#### 当服务器数量增长时（> 10 台）
1. **并发拉取优化**：
   - 使用 `asyncio.gather()` 并发拉取所有 agent
   - 设置连接池复用 HTTP 连接
   
2. **数据库优化**：
   - 迁移到 PostgreSQL
   - 启用 TimescaleDB 扩展（原生时序数据库）

3. **缓存优化**：
   - 使用 Redis 替代内存 dict（支持持久化和分布式）
   - 前端增加缓存层（Service Worker）

4. **历史数据降采样**：
   - 7 天前数据降为 4 小时粒度
   - 30 天前数据归档到对象存储

---

### 11.6 备份与恢复

#### 数据库备份脚本（PowerShell）

创建 `ops/monitor/scripts/backup-db.ps1`：

```powershell
# 每日备份脚本
$DateStr = Get-Date -Format "yyyyMMdd"
$BackupDir = "ops\monitor\backup"
$DbPath = "ops\monitor\data\monitor.db"
$BackupPath = "$BackupDir\monitor-$DateStr.db"

# 创建备份目录
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# 备份数据库
Copy-Item $DbPath $BackupPath -Force

# 清理 7 天前的备份
Get-ChildItem $BackupDir -Filter "monitor-*.db" | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-7)
} | Remove-Item -Force

Write-Host "Backup completed: $BackupPath"
```

#### 恢复数据库

```powershell
# 停止 aggregator 服务
# 恢复备份
Copy-Item ops\monitor\backup\monitor-20260117.db ops\monitor\data\monitor.db -Force
# 重启 aggregator 服务
```

```

---

## 12. 下一步（如果你要我继续实现）

### 12.1 已确认信息
你已经确认：
- ✅ 3 台 Linux 服务器
- ✅ GPU 全部为 NVIDIA
- ✅ 中心节点为 Windows（本仓库所在机器）
- ✅ 使用 NSSM 框架托管服务
- ✅ 前端推荐使用 Tabler 模板

### 12.2 待确认信息
还需要你提供：
1. **服务器详细信息**（用于初始化 `servers` 表）：
   - 每台服务器的 IP 地址
   - 每台服务器的名称（如 `gpu-server-01`）
   - （可选）每台需要监控的 systemd 服务清单（如不确定可先留空，后续通过前端"发现服务"功能添加）

2. **部署偏好**：
   - aggregator 使用什么语言实现？
     - **Python**（推荐，与你现有项目栈一致，FastAPI + SQLite + asyncio）
     - **Node.js**（Express + SQLite/better-sqlite3）
     - **Go**（性能最优，但开发周期稍长）

### 12.3 实施检查清单

在我开始实现代码之前，请确认以下前置条件：

#### Linux 端（每台服务器）
- [ ] 已安装 Python 3.8+（用于 agent）
- [ ] 已安装 NVIDIA 驱动并可执行 `nvidia-smi`
- [ ] 可以从中心节点访问（网络互通）
- [ ] 准备了一个用于 agent 的 token（或让我生成）

#### Windows 中心节点
- [ ] 已安装 Python 3.8+（如选择 Python 实现）
- [ ] 已安装 SQLite3（或我在实现时提供便携版）
- [ ] NSSM 框架可正常使用
- [ ] 确认前端监听端口（如 `8080`）

### 12.4 我将交付的内容

一旦你确认以上信息，我将提供：

1. **Agent 代码**（`ops/monitor-agent/`）
   - Python 模块，包含 FastAPI 服务
   - 配置文件模板
   - systemd 服务文件
   - 部署脚本（自动化安装）

2. **Aggregator 代码**（`ops/monitor/aggregator/`）
   - 5s 采集循环
   - 小时聚合任务
   - REST API（含完整端点实现）
   - 数据库 schema 初始化脚本
   - NSSM 服务配置文件

3. **前端 Dashboard**（`ops/monitor/frontend/`）
   - 基于 Tabler 的静态页面
   - 概览页、详情页、服务器管理页、事件页
   - 5s 自动刷新
   - 完整的 UI/UX 实现

4. **部署文档**（`ops/monitor/README.md`）
   - 一键部署脚本（PowerShell + Bash）
   - 配置说明
   - 快速启动指南
   - 常见问题 FAQ

