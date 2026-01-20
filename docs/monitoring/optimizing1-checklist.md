# Optimizing1 验收清单

本清单用于验证 Optimizing1 迭代（历史页 + 多GPU展示 + 代理端口转发）的功能完整性。

---

## M0：数据库升级

### 迁移验证
- [ ] 备份文件已创建（`backup/monitor-pre-v1.1-*.db`）
- [ ] `upgrade-to-v1.1.ps1` 执行无报错
- [ ] `servers` 表包含 `proxy_config` 字段
- [ ] `samples_hourly` 表包含 `gpu_details` 字段
- [ ] `schema_migrations` 记录版本 `1.1.0`

### 回滚验证
- [ ] `rollback-v1.1.sql` 可成功执行
- [ ] 回滚后表结构恢复到 v1.0
- [ ] 现有数据未丢失

---

## M1：历史页可用

### 后端 API
- [ ] `GET /api/history/hourly` 返回正确数据
- [ ] 支持 `server_id` 筛选
- [ ] 支持 `from`/`to` 时间范围筛选
- [ ] 支持分页（`limit`/`offset`）
- [ ] 单次最多返回 1000 条
- [ ] 响应时间 < 2s

### 前端功能
- [ ] 侧边栏显示「历史」入口
- [ ] 服务器多选筛选正常
- [ ] 时间范围选择正常
- [ ] 快捷按钮正常（24h/7d/30d）
- [ ] 表格分页正常（20条/页）
- [ ] 表格排序正常
- [ ] CSV 导出功能正常

---

## M2：多GPU展示

### Agent 端
- [ ] `/v1/snapshot` 返回完整 `gpus` 数组
- [ ] 每个 GPU 包含 `index`, `name`, `util_pct`, `mem_used_mb`, `mem_total_mb`
- [ ] 包含 `temperature_c`（可选）
- [ ] 单卡采集失败不影响其他卡
- [ ] 无 GPU 时返回 `gpus: null`

### Aggregator 端
- [ ] `LatestSnapshot` 包含 `gpus` 数组
- [ ] `gpu_count` 字段正确
- [ ] 兼容字段计算正确：
  - [ ] `gpu_util_pct` = max(各卡 util)
  - [ ] `gpu_util_pct_avg` = avg(各卡 util)
  - [ ] `gpu_mem_used_mb` = sum(各卡 mem_used)

### 前端展示
- [ ] **概览页**：显示 GPU 数量
- [ ] **概览页**：迷你条形图显示每卡 utilization
- [ ] **概览页**：条形图可折叠
- [ ] **详情页**：GPU 列表表格
- [ ] **详情页**：显示 index/name/util/mem/温度
- [ ] **详情页**：温度 > 80°C 标红警告
- [ ] **无 GPU**：显示「无 GPU 设备」

---

## M3：代理转发

### Windows 中心节点
- [ ] OpenSSH Server 已安装
- [ ] `sshd` 服务运行中
- [ ] 防火墙规则已配置（TCP 22）
- [ ] `administrators_authorized_keys` 权限正确
- [ ] 代理服务运行中（127.0.0.1:7879）

### Linux Agent
- [ ] SSH 密钥已生成（ed25519）
- [ ] 公钥已添加到中心节点
- [ ] SSH 连接测试成功
- [ ] Agent 配置包含 proxy 块

### Agent API
- [ ] `GET /v1/proxy/status` 返回状态
- [ ] `POST /v1/proxy/start` 可启动代理
- [ ] `POST /v1/proxy/stop` 可停止代理
- [ ] 断线自动重连（指数退避）
- [ ] 日志记录连接/断线事件

### Aggregator API
- [ ] `GET /api/servers/{id}/proxy` 返回配置+状态
- [ ] `PUT /api/servers/{id}/proxy` 可保存配置
- [ ] `action: "start"` 触发启动
- [ ] `action: "stop"` 触发停止
- [ ] 错误正确传递

### 前端 UI
- [ ] 服务器管理：代理配置表单
- [ ] 配置表单：所有字段可编辑
- [ ] 详情页：状态卡片显示
- [ ] 详情页：启停按钮
- [ ] 显示 `last_error`
- [ ] 显示 `retry_count`
- [ ] 显示 `connected_since`

### 功能验证
- [ ] 代理启动后 `status` 为 `connected`
- [ ] `curl -x http://127.0.0.1:8080 https://example.com` 成功
- [ ] 手动断开 SSH 后自动重连
- [ ] 重连后 UI 状态更新

---

## M4：回归测试

### 现有功能
- [ ] 概览页正常加载
- [ ] 服务器详情页正常
- [ ] 时间序列图表正常
- [ ] 服务器管理 CRUD 正常
- [ ] 事件页正常
- [ ] 5s 自动刷新正常

### 数据完整性
- [ ] 升级后历史数据完整
- [ ] 新数据正常写入
- [ ] 每小时聚合正常

### 兼容性
- [ ] API 向后兼容
- [ ] 无 GPU 服务器正常工作
- [ ] 未配置代理的服务器正常工作

---

## 文档验收

- [ ] `optimizing1-upgrade-guide.md` - 升级指南完整
- [ ] `proxy-setup-guide.md` - 配置步骤清晰
- [ ] `proxy-troubleshooting.md` - 故障排查覆盖常见问题
- [ ] `optimizing1-checklist.md` - 验收清单完整

---

## 脚本验收

### 数据库脚本
- [ ] `migration-v1.1.sql` - 迁移成功
- [ ] `rollback-v1.1.sql` - 回滚成功
- [ ] `upgrade-to-v1.1.ps1` - 自动化升级成功

### 部署脚本
- [ ] `setup-ssh-keys.sh` - 密钥生成成功
- [ ] `setup-openssh-server.ps1` - OpenSSH 配置成功

---

## 签署

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| AI-A (Agent) | | | |
| AI-B (Aggregator) | | | |
| AI-C (Frontend) | | | |
| AI-D (Schema & Docs) | | | |
| 验收人 | | | |

---

## 备注

_记录验收过程中的问题或特殊情况：_

```
- 
- 
- 
```
