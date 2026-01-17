# 监控系统多 AI 协作分工方案

> 本文档定义 4 个独立模块的职责边界、接口规范和工作范围，确保多个 AI 可并行开发而不相互干扰

---

## 分工原则

1. **模块独立性**：每个模块有独立的目录，不交叉修改文件
2. **接口优先**：先定义接口契约，再并行实现
3. **数据格式统一**：所有时间戳使用 ISO 8601 格式，所有百分比为 0~100 浮点数
4. **配置独立**：每个模块有自己的配置文件

---

## 任务分配（4 个独立任务）

### 任务 A：Agent 端实现（Linux Agent）
**负责 AI**：AI-A  
**工作目录**：`ops/monitor/agent/`  
**预计工作量**：中等（约 500 行代码）

### 任务 B：Aggregator 端实现（Windows 中心节点）
**负责 AI**：AI-B  
**工作目录**：`ops/monitor/aggregator/`  
**预计工作量**：大（约 800 行代码）

### 任务 C：Frontend 端实现（Web Dashboard）
**负责 AI**：AI-C  
**工作目录**：`ops/monitor/frontend/`  
**预计工作量**：中等（约 600 行代码）

### 任务 D：数据库 Schema 与部署脚本
**负责 AI**：AI-D  
**工作目录**：`ops/monitor/` 根目录 + `ops/monitor/scripts/`  
**预计工作量**：小（约 300 行代码）

---

## 接口契约（必须严格遵守）

### 1. Agent API 接口（AI-A 提供，AI-B 调用）

#### 1.1 `GET /v1/snapshot`

**请求**：
```http
GET /v1/snapshot HTTP/1.1
Host: <agent-ip>:9109
Authorization: Bearer <token>
```

**响应**（200 OK）：
```json
{
  "node_id": "srv-01",
  "ts": "2026-01-17T20:00:00Z",
  "cpu_pct": 23.4,
  "disks": [
    {
      "mount": "/",
      "used_bytes": 123456789,
      "total_bytes": 500000000000,
      "used_pct": 24.7
    }
  ],
  "gpus": [
    {
      "index": 0,
      "util_pct": 85.0,
      "mem_used_mb": 6144,
      "mem_total_mb": 8192
    }
  ],
  "services": [
    {
      "name": "nginx.service",
      "active_state": "active",
      "sub_state": "running"
    }
  ]
}
```

**字段说明**：
- `ts`：采集时间（ISO 8601 格式，UTC）
- `cpu_pct`：0~100 浮点数，null 表示首次采样未就绪
- `disks`：数组，至少包含根分区 `/`
- `gpus`：数组或 null（无 GPU 时）
- `services`：数组，可为空（未配置服务监控时）

**错误响应**：
- `401 Unauthorized`：Token 错误
- `500 Internal Server Error`：采集失败

---

#### 1.2 `GET /v1/health`

**请求**：
```http
GET /v1/health HTTP/1.1
Host: <agent-ip>:9109
```

**响应**（200 OK）：
```json
{
  "status": "ok",
  "timestamp": "2026-01-17T20:00:00Z",
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

**status 枚举**：`ok` | `degraded` | `error`

---

#### 1.3 `GET /v1/services`

**请求**：
```http
GET /v1/services HTTP/1.1
Host: <agent-ip>:9109
Authorization: Bearer <token>
```

**响应**（200 OK）：
```json
[
  {
    "name": "nginx.service",
    "active_state": "active",
    "enabled": true,
    "description": "A high performance web server"
  }
]
```

---

### 2. Aggregator API 接口（AI-B 提供，AI-C 调用）

#### 2.1 `GET /api/servers`

**响应**：
```json
[
  {
    "id": 1,
    "name": "srv-01",
    "host": "10.0.0.101",
    "agent_port": 9109,
    "enabled": true,
    "online": true,
    "last_seen_at": "2026-01-17T19:59:55Z",
    "latest": {
      "ts": "2026-01-17T19:59:55Z",
      "cpu_pct": 23.4,
      "disk_used_pct": 67.2,
      "disk_used_bytes": 123456789,
      "disk_total_bytes": 500000000000,
      "gpu_util_pct": 85.0,
      "gpu_mem_used_mb": 6144,
      "gpu_mem_total_mb": 8192,
      "services_failed_count": 0
    }
  }
]
```

**注意**：
- `latest` 可能为 `null`（从未成功拉取过）
- `online` 判断：`now - last_seen_at < 12s`

---

#### 2.2 `POST /api/servers`

**请求**：
```json
{
  "name": "srv-01",
  "host": "10.0.0.101",
  "agent_port": 9109,
  "token": "abc123...",
  "services": ["nginx.service", "docker.service"],
  "enabled": true
}
```

**响应**（201 Created）：
```json
{
  "id": 1,
  "name": "srv-01",
  "created_at": "2026-01-17T20:00:00Z"
}
```

---

#### 2.3 `GET /api/servers/{id}/timeseries`

**请求参数**：
- `metric`：`cpu_pct` | `disk_used_pct` | `gpu_util_pct`
- `from`：ISO 8601 时间（如 `2026-01-17T00:00:00Z`）
- `to`：ISO 8601 时间
- `agg`：`avg` | `max`（默认 `avg`）

**响应**：
```json
{
  "server_id": 1,
  "metric": "cpu_pct",
  "agg": "avg",
  "data": [
    {"ts": "2026-01-17T10:00:00Z", "value": 23.4},
    {"ts": "2026-01-17T11:00:00Z", "value": 45.2}
  ]
}
```

---

#### 2.4 `GET /api/events`

**请求参数**：
- `limit`：整数（默认 200）

**响应**：
```json
[
  {
    "id": 1,
    "server_id": 1,
    "server_name": "srv-01",
    "ts": "2026-01-17T19:30:00Z",
    "type": "server_down",
    "message": "Server went offline"
  }
]
```

---

### 3. 数据库 Schema（AI-D 提供，AI-B 使用）

**表结构定义**（详见 `schema.sql`）：

#### `servers` 表
```sql
CREATE TABLE servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    host TEXT NOT NULL,
    agent_port INTEGER DEFAULT 9109,
    enabled INTEGER DEFAULT 1,
    services TEXT,  -- JSON 数组字符串
    token TEXT NOT NULL,
    last_seen_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

#### `samples_hourly` 表
```sql
CREATE TABLE samples_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    ts TEXT NOT NULL,  -- 格式："2026-01-17 10:00:00"
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
```

#### `events` 表
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,  -- server_down|server_up|service_failed|service_recovered
    message TEXT,
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);
```

**重要约定**：
- SQLite TEXT 类型存储时间，格式严格为 ISO 8601
- `enabled` 字段：1 = true, 0 = false
- `services` 字段：JSON 字符串数组（如 `["nginx.service", "docker.service"]`）

---

## 任务详细说明

### 任务 A：Agent 端实现（AI-A）

**目标**：创建轻量级 Linux Agent，提供 HTTP 接口供中心节点拉取数据

#### 文件清单（只能修改这些文件）
```
ops/monitor/agent/
├── monitor_agent/
│   ├── __init__.py
│   ├── app.py                    # FastAPI 应用（主要）
│   ├── config.py                 # 配置加载
│   ├── models.py                 # Pydantic 数据模型
│   ├── utils.py                  # 工具函数
│   └── collectors/
│       ├── __init__.py
│       ├── cpu.py                # CPU 采集器
│       ├── disk.py               # 磁盘采集器
│       ├── gpu.py                # GPU 采集器（NVIDIA）
│       └── systemd.py            # systemd 服务采集器
├── requirements.txt              # Python 依赖
├── setup.py                      # 打包配置（可选）
└── config.example.yaml           # 配置文件模板
```

#### 核心任务
1. **实现 3 个 API 端点**（严格遵守上述接口契约）
2. **实现 4 个采集器**：
   - `cpu.py`：读取 `/proc/stat` 计算 CPU 使用率
   - `disk.py`：使用 `psutil.disk_usage()` 或解析 `df`
   - `gpu.py`：调用 `nvidia-smi` 解析输出，无 GPU 时返回 None
   - `systemd.py`：调用 `systemctl show` 查询服务状态
3. **配置管理**：从 `/etc/monitor-agent/config.yaml` 加载配置
4. **异常处理**：单个采集器失败不影响整体响应
5. **Token 验证**：Bearer 方式验证（简单字符串比对即可）

#### 技术约束
- Python 3.8+
- FastAPI + Uvicorn
- psutil（可选，也可直接读 `/proc`）
- 异步实现（`async/await`）
- 资源占用 < 100MB 内存

#### 测试要求
提供一个测试脚本 `test_agent.py`：
```python
# 启动 agent 后测试
import requests

response = requests.get(
    "http://localhost:9109/v1/snapshot",
    headers={"Authorization": "Bearer test-token"}
)
print(response.json())
```

#### 依赖其他任务
- ❌ 无依赖（完全独立）

---

### 任务 B：Aggregator 端实现（AI-B）

**目标**：创建中心节点服务，负责采集、聚合、存储和 API

#### 文件清单（只能修改这些文件）
```
ops/monitor/aggregator/
├── monitor_aggregator/
│   ├── __init__.py
│   ├── main.py                   # 主程序入口（启动 3 个并发任务）
│   ├── config.py                 # 配置加载
│   ├── models.py                 # 数据模型（内存缓存）
│   ├── database.py               # 数据库操作抽象层
│   ├── collector.py              # 5s 采集循环
│   ├── aggregator.py             # 小时聚合任务
│   ├── event_detector.py         # 事件检测逻辑
│   └── api/
│       ├── __init__.py
│       ├── app.py                # FastAPI 应用
│       ├── dependencies.py       # 依赖注入
│       └── routers/
│           ├── __init__.py
│           ├── servers.py        # 服务器管理 API
│           ├── timeseries.py     # 时间序列 API
│           └── events.py         # 事件 API
├── requirements.txt
└── service.json                   # NSSM 服务配置
```

#### 核心任务
1. **5s 采集循环**（`collector.py`）：
   - 并发拉取所有 agent（`httpx.AsyncClient`）
   - 更新 `server_latest` 内存缓存
   - 追加到 `hourly_buffer`
   - 调用事件检测
   
2. **小时聚合任务**（`aggregator.py`）：
   - 等到整点触发
   - 计算 avg/max
   - 写入 `samples_hourly` 表
   - 清空缓冲区

3. **事件检测**（`event_detector.py`）：
   - 比较当前状态与上一次状态
   - 检测在线状态变化、服务失败/恢复
   - 写入 `events` 表

4. **数据库抽象层**（`database.py`）：
   - SQLite 连接管理（上下文管理器）
   - CRUD 操作（增删改查服务器、保存样本、查询时序数据）
   - 事务支持

5. **REST API**（`api/`）：
   - 实现所有接口（严格遵守上述契约）
   - CORS 支持（允许前端跨域）
   - 静态文件托管（`/` 路径映射到 `../frontend/`）

#### 技术约束
- Python 3.8+
- FastAPI + Uvicorn
- asyncio 并发
- SQLite3（标准库）
- httpx（HTTP 客户端）

#### 配置文件示例
```yaml
# ops/monitor/config.yaml
database_path: "ops/monitor/data/monitor.db"
api_host: "0.0.0.0"
api_port: 8080
frontend_path: "ops/monitor/frontend"
```

#### 依赖其他任务
- ✅ 依赖任务 D（数据库 schema）
- ⚠️ 调用任务 A（Agent API），但可独立开发（用 mock 数据）

---

### 任务 C：Frontend 端实现（AI-C）

**目标**：创建 Web Dashboard，提供可视化界面

#### 文件清单（只能修改这些文件）
```
ops/monitor/frontend/
├── index.html                    # 概览页
├── server-detail.html            # 服务器详情页
├── servers-manage.html           # 服务器管理页
├── events.html                   # 事件页
├── config.js                     # 前端配置（API 地址）
└── assets/
    ├── css/
    │   ├── tabler.min.css        # Tabler 框架（CDN 或本地）
    │   └── custom.css            # 自定义样式
    ├── js/
    │   ├── tabler.min.js
    │   ├── echarts.min.js        # ECharts 图表库
    │   ├── api-client.js         # API 客户端封装
    │   ├── overview.js           # 概览页逻辑
    │   ├── server-detail.js      # 详情页逻辑
    │   ├── servers-manage.js     # 管理页逻辑
    │   └── events.js             # 事件页逻辑
    └── img/
```

#### 核心任务
1. **概览页**（`index.html` + `overview.js`）：
   - 服务器卡片网格（在线状态、CPU/磁盘/GPU 进度条）
   - 5s 自动刷新（`setInterval`）
   - 点击跳转详情页

2. **详情页**（`server-detail.html` + `server-detail.js`）：
   - 显示服务器基本信息
   - ECharts 时间序列图表（CPU/磁盘/GPU）
   - 时间范围切换（1h/6h/24h/7d）
   - 服务状态列表

3. **管理页**（`servers-manage.html` + `servers-manage.js`）：
   - 表格展示所有服务器
   - 添加/编辑/删除服务器
   - "发现服务"按钮（调用 `/api/servers/{id}/services/catalog`）

4. **事件页**（`events.html` + `events.js`）：
   - 时间线展示
   - 事件类型过滤

5. **API 客户端**（`api-client.js`）：
   - 封装所有 API 调用
   - 统一错误处理
   - 支持配置 API 基础 URL

#### 技术约束
- 纯 HTML/JS/CSS（无需构建工具）
- Tabler 框架（Bootstrap 5）
- ECharts 图表库
- 原生 `fetch()` API
- 兼容现代浏览器（Chrome/Firefox/Edge）

#### 配置文件
```javascript
// config.js
const API_BASE = 'http://localhost:8080';
```

#### 依赖其他任务
- ✅ 依赖任务 B（Aggregator API）
- ⚠️ 可独立开发（先用 mock 数据，后期对接真实 API）

---

### 任务 D：数据库 Schema 与部署脚本（AI-D）

**目标**：创建数据库初始化脚本和部署工具

#### 文件清单（只能修改这些文件）
```
ops/monitor/
├── schema.sql                    # 数据库初始化 SQL
├── config.yaml                   # Aggregator 配置文件模板
├── README.md                     # 部署文档
└── scripts/
    ├── deploy-agent.sh           # Agent 部署脚本（Linux）
    ├── init-db.ps1               # 数据库初始化（PowerShell）
    ├── backup-db.ps1             # 数据库备份（PowerShell）
    └── health-check.ps1          # 健康巡检（PowerShell）
```

#### 核心任务
1. **数据库 Schema**（`schema.sql`）：
   - 创建 4 张表（严格遵守上述定义）
   - 创建索引
   - 设置 WAL 模式
   - 支持幂等执行（`IF NOT EXISTS`）

2. **Agent 部署脚本**（`deploy-agent.sh`）：
   - 参数：服务器 IP、node_id、token
   - 自动化：创建用户、上传代码、安装依赖、配置 systemd、启动服务
   - 防火墙配置提示

3. **数据库初始化**（`init-db.ps1`）：
   - 检查数据库是否存在
   - 创建目录结构
   - 执行 `schema.sql`

4. **备份脚本**（`backup-db.ps1`）：
   - 每日备份到 `backup/` 目录
   - 清理 7 天前备份

5. **健康巡检**（`health-check.ps1`）：
   - 检查 aggregator 服务状态
   - 检查 API 可用性
   - 检查数据库大小
   - 测试每台 agent 连通性

6. **部署文档**（`README.md`）：
   - 快速启动指南
   - 分步部署说明
   - 常见问题 FAQ

#### 技术约束
- SQLite 标准 SQL
- Bash（Linux 脚本）
- PowerShell 5.1+（Windows 脚本）

#### 依赖其他任务
- ❌ 无依赖（优先完成，其他任务依赖此任务）

---

## 协作流程建议

### 阶段 1：接口定义（已完成） ✅
- 本文档已完成接口契约定义
- 所有 AI 确认理解接口规范

### 阶段 2：并行开发（可同时进行）
```
AI-D（优先） → 完成数据库 schema
    ↓
AI-A         → 实现 Agent（独立，可用 mock 测试）
AI-B         → 实现 Aggregator（依赖 schema，可 mock Agent）
AI-C         → 实现 Frontend（可 mock API 数据）
```

### 阶段 3：集成测试
1. AI-D 初始化数据库
2. AI-B 启动 aggregator（先不拉取 agent，测试 API）
3. AI-C 对接真实 API（替换 mock）
4. AI-A 部署 agent 到 Linux
5. AI-B 配置 aggregator 拉取 agent
6. 端到端测试

### 阶段 4：优化与文档
- 每个 AI 补充自己模块的测试用例
- 更新部署文档

---

## 文件冲突避免规则

| 目录/文件 | 负责 AI | 其他 AI 权限 |
|-----------|---------|--------------|
| `ops/monitor/agent/` | AI-A | ❌ 禁止修改 |
| `ops/monitor/aggregator/` | AI-B | ❌ 禁止修改 |
| `ops/monitor/frontend/` | AI-C | ❌ 禁止修改 |
| `ops/monitor/schema.sql` | AI-D | ✅ 只读（AI-B 执行） |
| `ops/monitor/scripts/` | AI-D | ❌ 禁止修改 |
| `ops/monitor/config.yaml` | AI-D | ✅ 只读（AI-B 加载） |
| `docs/monitoring/*.md` | 所有 | ✅ 只读（参考架构） |

---

## 沟通约定

### 场景 1：发现接口问题
**示例**：AI-C 发现 `/api/servers` 返回格式缺少字段

**流程**：
1. AI-C 在本文档 issues 区记录问题
2. AI-B 确认并修改
3. 更新接口契约版本号

### 场景 2：需要新增接口
**示例**：AI-C 需要批量删除服务器接口

**流程**：
1. AI-C 提出需求并设计接口草案
2. 其他 AI 审核
3. 达成一致后更新接口契约
4. AI-B 实现

### 场景 3：配置变更
**示例**：AI-B 需要修改默认端口

**流程**：
1. AI-B 更新 `config.yaml` 模板
2. 通知 AI-C 更新 `config.js` 默认值
3. AI-D 更新部署文档

---

## 版本管理建议

每个模块独立版本：
- Agent: v1.0.0
- Aggregator: v1.0.0
- Frontend: v1.0.0
- Scripts: v1.0.0

接口契约版本：v1.0（本文档）

**兼容性保证**：
- 接口契约 v1.x 内向后兼容
- 新增字段可选，不删除已有字段

---

## 质量检查清单

### AI-A 完成标准
- [ ] 3 个 API 端点测试通过
- [ ] 4 个采集器单元测试通过
- [ ] 响应格式符合接口契约
- [ ] Token 验证正常
- [ ] 资源占用 < 100MB

### AI-B 完成标准
- [ ] 5s 采集循环稳定运行
- [ ] 小时聚合任务正确执行
- [ ] 所有 API 端点测试通过
- [ ] 事件检测逻辑正确
- [ ] 数据库操作无泄漏

### AI-C 完成标准
- [ ] 4 个页面渲染正常
- [ ] 5s 自动刷新生效
- [ ] 图表显示正确
- [ ] 服务器 CRUD 功能完整
- [ ] 跨浏览器兼容

### AI-D 完成标准
- [ ] 数据库初始化成功
- [ ] Agent 部署脚本可用
- [ ] 备份脚本测试通过
- [ ] 部署文档清晰完整

---

## 时间估算

基于并行开发：

| 阶段 | 时间 | 关键路径 |
|------|------|----------|
| 阶段 1：接口定义 | ✅ 已完成 | - |
| 阶段 2：并行开发 | 2-3 天 | AI-B（最复杂） |
| 阶段 3：集成测试 | 0.5 天 | 全员 |
| 阶段 4：优化与文档 | 0.5 天 | 全员 |
| **总计** | **3-4 天** | - |

如果由单个 AI 完成：**5-7 天**

并行带来的效率提升：**约 40%**

---

## 开始实施

准备好后，请按以下顺序启动：

1. **优先启动 AI-D**：完成 schema.sql 和基础脚本
2. **其他 3 个 AI 同时启动**：各自负责模块
3. **定期同步**：每个模块完成阶段性工作后发布通知

祝协作顺利！🚀
