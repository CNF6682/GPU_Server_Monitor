-- ============================================================================
-- 监控系统数据库迁移脚本 v1.0 -> v1.1
-- 
-- 版本: 1.1.0
-- 日期: 2026-01-20
-- 说明: 
--   1. servers 表新增 proxy_config 字段（代理转发配置）
--   2. samples_hourly 表新增 gpu_details 字段（多GPU历史明细）
-- 
-- 用法: sqlite3 monitor.db < migration-v1.1.sql
-- 回滚: sqlite3 monitor.db < rollback-v1.1.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 版本检查提示
-- ----------------------------------------------------------------------------
-- 注意：SQLite 不支持条件 ALTER TABLE，此脚本幂等设计
-- 如果字段已存在，会报错但不影响数据

-- ----------------------------------------------------------------------------
-- Step 1: servers 表 - 新增 proxy_config 字段
-- ----------------------------------------------------------------------------
-- 说明：存储代理转发配置（JSON格式）
-- 示例值：
-- {
--   "enabled": true,
--   "server_listen_port": 8080,
--   "center_proxy_port": 7879,
--   "center_ssh_host": "10.0.0.2",
--   "center_ssh_port": 22,
--   "center_ssh_user": "dhga",
--   "identity_file": "/home/dhga/.ssh/id_ed25519",
--   "strict_host_key_checking": true,
--   "auto_start": false
-- }

ALTER TABLE servers ADD COLUMN proxy_config TEXT;

-- ----------------------------------------------------------------------------
-- Step 2: samples_hourly 表 - 新增 gpu_details 字段
-- ----------------------------------------------------------------------------
-- 说明：存储多GPU历史明细（JSON格式）
-- 示例值：
-- [
--   {"index": 0, "name": "NVIDIA A100", "util_pct_avg": 85.5, "util_pct_max": 95.0, 
--    "mem_used_mb": 20480, "mem_total_mb": 40960, "temperature_c": 75.0},
--   {"index": 1, "name": "NVIDIA A100", "util_pct_avg": 62.3, "util_pct_max": 88.0, 
--    "mem_used_mb": 15360, "mem_total_mb": 40960, "temperature_c": 72.0}
-- ]
-- 
-- 注意：现有的 gpu_util_pct_avg/max、gpu_mem_used/total_mb 字段保留用于向后兼容
-- 新增字段提供更详细的多GPU信息

ALTER TABLE samples_hourly ADD COLUMN gpu_details TEXT;

-- ----------------------------------------------------------------------------
-- Step 3: 创建版本记录表（可选，用于追踪迁移历史）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- 记录此次迁移
INSERT OR REPLACE INTO schema_migrations (version, description) 
VALUES ('1.1.0', 'Add proxy_config to servers, gpu_details to samples_hourly');

-- ----------------------------------------------------------------------------
-- 迁移完成
-- ----------------------------------------------------------------------------
-- 验证命令：
-- sqlite3 monitor.db "PRAGMA table_info(servers);"
-- sqlite3 monitor.db "PRAGMA table_info(samples_hourly);"
-- sqlite3 monitor.db "SELECT * FROM schema_migrations;"
