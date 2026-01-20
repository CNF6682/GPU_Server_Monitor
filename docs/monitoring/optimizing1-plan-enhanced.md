# Optimizing1 迭代计划（增强版）：历史页 + 多 GPU 展示 + 代理端口转发

> 目标：在现有监控系统基础上，补齐历史查询、多GPU明细、代理转发三项能力，保持架构兼容性。

---

## 0. 范围与非目标

### 本次新增
1. **历史信息独立选项卡**：侧边栏新增「历史」入口，查看 `samples_hourly` 历史（表格/筛选/导出）
2. **多 GPU 数量与占用**：展示 GPU 数量与每块 GPU 的使用率/显存（实时+历史）
3. **代理端口转发服务**：服务器通过 SSH 隧道访问中心节点代理

### 非目标
- 分钟级/秒级历史入库（仍保持每小时1条）
- 复杂鉴权/多租户/公网暴露
- 自动化 Windows OpenSSH 安装（仅提供脚本指引）

---

## 1. 现状要点

- **Agent**：`GET /v1/snapshot` 已返回 `gpus` 数组（NVIDIA场景）
- **Aggregator**：当前仅取 `gpus[0]` 作为 GPU 指标
- **Frontend**：缺少历史记录全局入口

---

## 2. 设计方案

### 2.1 历史信息（独立选项卡）

**前端**：新增 `history.html`
- 筛选：服务器（多选）、时间范围、排序
- 导出 CSV（前端生成或后端接口）

**后端**：新增 API
```
GET /api/history/hourly?server_id=&from=&to=&limit=&offset=
返回：[{server_id, ts, cpu_pct_avg, cpu_pct_max, ...}]
限制：单次最多1000条
```

### 2.2 多 GPU 实时展示

**数据模型增强**：
```python
# GPUInfo 结构
{
  "index": 0,
  "name": "NVIDIA A100",
  "util_pct": 85.5,
  "mem_used_mb": 20480,
  "mem_total_mb": 40960,
  "temperature_c": 75.0  # 可选
}

# LatestSnapshot 新增字段
{
  "gpus": [GPUInfo, ...] | null,
  "gpu_count": 4,
  # 兼容字段（向后兼容）
  "gpu_util_pct": max(gpus.util_pct),      # 最忙GPU
  "gpu_util_pct_avg": avg(gpus.util_pct),  # 新增：平均利用率
  "gpu_mem_used_mb": sum(gpus.mem_used),
  "gpu_mem_total_mb": sum(gpus.mem_total)
}
```

**历史聚合策略**：
- 现有字段保持不变（兼容性）
- 可选：新增 `samples_hourly.gpu_details` (JSON) 存储每卡历史

**前端展示**：
- 概览：GPU数量 + 迷你条形图（每卡utilization，可折叠）
- 详情：GPU列表表格（index/name/util/mem/温度）
- 容错：无GPU显示"无GPU设备"

### 2.3 代理端口转发服务

**核心机制**：SSH 本地端口转发（-L）
```bash
ssh -N -L 127.0.0.1:8080:127.0.0.1:7879 \
    user@center_host -p 22 -i ~/.ssh/id_ed25519 \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=yes
```

**可靠性保障**：
- 进程管理：`subprocess.Popen` + PID跟踪
- 重连策略：指数退避（1s→2s→4s→8s，最大60s）
- 错误码：`PORT_IN_USE`, `AUTH_FAILED`, `NETWORK_UNREACHABLE`
- 日志：连接/断线事件（INFO）+ 错误详情（ERROR）

**安全措施**：
- 默认仅绑定 `127.0.0.1`（不暴露外网）
- 强制密钥认证（不支持密码）
- 配置文件权限：600

**Agent API**：
```
GET /v1/proxy/status
返回：{status, pid, listen_port, target, last_error, connected_since, retry_count}

POST /v1/proxy/start  # 启动/重启
POST /v1/proxy/stop   # 优雅停止（SIGTERM→5s→SIGKILL）
```

**Aggregator API**：
```
GET /api/servers/{id}/proxy   # 读取配置+实时status
PUT /api/servers/{id}/proxy   # 保存配置+触发start/stop
  Body: {"config": {...}, "action": "start"|"stop"|null}
```

**数据库字段**：
```json
servers.proxy_config (TEXT): {
  "enabled": true,
  "server_listen_port": 8080,
  "center_proxy_port": 7879,
  "center_ssh_host": "10.0.0.2",
  "center_ssh_port": 22,
  "center_ssh_user": "dhga",
  "identity_file": "/home/dhga/.ssh/id_ed25519",
  "strict_host_key_checking": true,
  "auto_start": false  # Agent启动时是否自动启动
}
```

---

## 3. 代码改动点

### 3.1 Agent（Linux）
- GPU采集：确保返回完整 `gpus` 数组（含name/temperature）
- 新增 `proxy_forwarder/`：进程管理 + API路由
- 配置：`config.example.yaml` 增加 proxy 配置块

### 3.2 Aggregator（Windows）
- Collector：保留完整 `gpus`，计算兼容字段
- Models：`LatestSnapshot` 扩展 + `ServerResponse` 更新
- DB：新增 `proxy_config` 字段（含CRUD）
- API：`/api/history/hourly`, `/api/servers/{id}/proxy`

### 3.3 Frontend
- 历史页：`history.html` + `history.js`（筛选/分页/导出）
- GPU展示：概览卡片 + 详情页 GPU列表
- 代理UI：服务器管理配置表单 + 详情页状态控制

### 3.4 Schema & Scripts
**数据库迁移**（`scripts/migration-v1.1.sql`）：
```sql
ALTER TABLE servers ADD COLUMN proxy_config TEXT;
ALTER TABLE samples_hourly ADD COLUMN gpu_details TEXT;  -- 可选
```

**升级脚本**（`scripts/upgrade-to-v1.1.ps1`）：
```powershell
# 1. 自动备份 monitor.db
# 2. 执行迁移SQL
# 3. 验证表结构
```

**部署工具**：
- Linux: `setup-ssh-keys.sh`（密钥生成+分发）
- Windows: `setup-openssh-server.ps1`（一键配置）

---

## 4. 分工安排（详细任务拆分）

### 任务 A（AI-A）：Agent 增强

**子任务**：
1. **GPU采集增强**
   - 返回完整 `gpus` 数组（含 name/temperature）
   - 异常容错（单卡失败不影响其他卡）

2. **代理转发模块**
   - `proxy_forwarder/manager.py`：进程管理+重连
   - `/v1/proxy/*` API 实现
   - 配置加载与校验

3. **文档与测试**
   - 更新 `config.example.yaml`
   - GPU数据格式文档（给AI-B参考）
   - 代理API测试脚本

**交付物**：
- `monitor_agent/proxy_forwarder/`（manager.py, config.py）
- API: `/v1/proxy/status`, `/v1/proxy/start`, `/v1/proxy/stop`
- 文档: `docs/agent-proxy-api.md`

---

### 任务 B（AI-B）：Aggregator 核心

**子任务**：
1. **多GPU数据模型**
   - Models: `GPUInfo`, `LatestSnapshot` 扩展
   - Collector: 计算兼容字段（max/avg/sum）

2. **历史查询API**
   - `GET /api/history/hourly`（分页/筛选）
   - 查询优化（索引+限制1000条）
   - 可选：CSV导出接口

3. **代理配置API**
   - DB: `proxy_config` CRUD
   - `GET/PUT /api/servers/{id}/proxy`
   - 调用Agent API（含错误处理）

4. **单元测试**
   - GPU聚合逻辑测试
   - 历史查询边界测试

**交付物**：
- 更新 `models.py`, `collector.py`, `database.py`
- API: `/api/history/hourly`, `/api/servers/{id}/proxy`
- 测试: `tests/test_aggregator_gpu.py`

---

### 任务 C（AI-C）：Frontend UI

**子任务**：
1. **历史页面**
   - `history.html` + `history.js`
   - 筛选：服务器多选、时间范围（快捷按钮）
   - 表格：分页（20/页）、排序
   - CSV导出

2. **多GPU展示**
   - 概览：GPU数量 + 迷你条形图（可折叠）
   - 详情：GPU列表表格（util/mem/温度）
   - 温度预警（>80°C标红）

3. **代理UI**
   - 服务器管理：配置表单（折叠面板）
   - 详情页：状态卡片 + 启停按钮
   - 显示最后连接时间

**交付物**：
- `history.html`, `assets/js/history.js`
- 更新 `overview.js`, `server-detail.js`, `servers-manage.js`
- 更新 `custom.css`

---

### 任务 D（AI-D）：Schema & 文档

**子任务**：
1. **数据库迁移**（1天）
   - `migration-v1.1.sql` + 升级/回滚脚本
   - 测试：空DB + 有数据DB

2. **部署工具**（1.5天）
   - `setup-ssh-keys.sh`, `setup-openssh-server.ps1`
   - 依赖检查脚本

3. **文档编写**（1天）
   - 升级指南（`optimizing1-upgrade-guide.md`）
   - 代理配置指南（`proxy-setup-guide.md`）
   - 故障排查（`proxy-troubleshooting.md`）
   - 验收清单（`optimizing1-checklist.md`）

**交付物**：
- SQL: `migration-v1.1.sql`, `rollback-v1.1.sql`
- 脚本: `upgrade-to-v1.1.ps1`, `setup-openssh-server.ps1`
- 完整文档集

---

## 5. 开发时间线

| 里程碑 | 关键交付物 | 预计 | 负责人 |
|--------|-----------|------|--------|
| **M0: 数据库升级** | 迁移脚本 | D+1 | AI-D |
| **M1: 历史页可用** | 后端API + 前端页面 | D+3 | AI-B, AI-C |
| **M2: 多GPU展示** | Agent增强 + Aggregator + UI | D+4 | AI-A, AI-B, AI-C |
| **M3: 代理转发** | 完整链路 | D+6 | AI-A, AI-B, AI-C |
| **M4: 完整验收** | E2E测试 + 文档 | D+7 | ALL |

**并行建议**：
- D1-2: AI-D迁移（优先），AI-A基础框架，AI-C UI设计
- D3-4: AI-B核心逻辑，AI-C前端开发
- D5-6: 代理功能集成
- D7: 联调测试

---

## 6. 风险与缓解

### 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 数据库迁移失败 | 高 | 低 | 强制备份 + 回滚脚本 + 测试验证 |
| SSH连接不稳定 | 中 | 中 | 指数退避重连 + 详细日志 + 故障文档 |
| 多GPU数据格式不一致 | 中 | 低 | Agent严格校验 + Aggregator防御检查 |
| 历史查询性能 | 低 | 中 | 限制1000条 + 时间索引 |
| 端口冲突 | 低 | 中 | 自定义端口 + 占用检测 + 明确错误 |

### 部署风险

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| Windows OpenSSH配置复杂 | 高 | 高 | 一键脚本 + 详细文档 |
| SSH密钥管理混乱 | 中 | 中 | 自动化脚本 + 权限文档 |
| 防火墙阻止 | 中 | 中 | 自动配置规则 + 手动说明 |

### 安全风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 代理被滥用 | 高 | 默认仅127.0.0.1 |
| SSH私钥泄露 | 高 | 强制权限600 + 管理规范 |
| 配置明文存储 | 中 | 独立密钥 + 文件权限 |

---

## 7. 验收标准

### M1：历史页可用
- ✓ 前端筛选服务器/时间并展示历史
- ✓ CSV导出功能正常
- ✓ 分页正常（每页20条）

### M2：多GPU展示
- ✓ 概览/详情显示GPU数量与每卡utilization
- ✓ 无GPU服务器显示"无GPU设备"
- ✓ 温度>80°C标红警告

### M3：代理转发
- ✓ UI配置并启动成功
- ✓ `curl -x http://127.0.0.1:8080 https://example.com` 成功
- ✓ 断线自动重连
- ✓ UI显示last_error和重试次数

### M4：回归测试
- ✓ 现有功能不受影响
- ✓ 数据库升级无数据丢失
- ✓ 所有文档完整

---

## 8. 边界条件

### 环境要求
**Windows 中心节点**：
- OpenSSH Server ≥ 7.6
- 防火墙允许SSH（TCP 22）
- 代理运行在 `127.0.0.1:7879`

**Linux 服务器**：
- 已安装 `openssh-client`
- Agent以非root运行（推荐）
- 网络可达中心节点

### 配置限制
- 代理转发：仅密钥认证
- 历史查询：单次最多1000条
- GPU数量：显示最多16块（数据无限制）
- API超时：10s

### 非功能性要求
- **可用性**：代理断线5分钟内重连
- **性能**：历史查询<2s（1000条）
- **安全**：敏感配置文件权限保护
- **兼容性**：保持API向后兼容

---

## 附录：关键文档清单

**必须交付**（AI-D负责）：
1. `docs/monitoring/optimizing1-upgrade-guide.md` - 升级指南
2. `docs/monitoring/proxy-setup-guide.md` - 代理配置详解
3. `docs/monitoring/proxy-troubleshooting.md` - 故障排查
4. `docs/monitoring/optimizing1-checklist.md` - 验收清单
5. `scripts/migration-v1.1.sql` - 数据库迁移
6. `scripts/upgrade-to-v1.1.ps1` - 自动升级脚本

**可选参考**（各AI补充）：
- `docs/agent-proxy-api.md` - Agent代理API文档（AI-A）
- `tests/test_proxy_integration.sh` - 代理集成测试（AI-A）
- `tests/test_aggregator_gpu.py` - GPU聚合测试（AI-B）
