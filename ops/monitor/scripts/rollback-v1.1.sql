-- ============================================================================
-- 监控系统数据库回滚脚本 v1.1 -> v1.0
-- 
-- 版本: 1.1.0 回滚
-- 日期: 2026-01-20
-- 说明: 回滚 migration-v1.1.sql 的更改
-- 
-- ⚠️  警告：
--   1. SQLite 不支持 DROP COLUMN（3.35.0 之前版本）
--   2. 此脚本通过重建表实现回滚
--   3. 执行前请确保已备份数据库！
-- 
-- 用法: sqlite3 monitor.db < rollback-v1.1.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 安全检查提示
-- ----------------------------------------------------------------------------
-- 执行前请先备份：
-- copy monitor.db monitor.db.backup

-- ----------------------------------------------------------------------------
-- Step 1: 回滚 samples_hourly 表（移除 gpu_details）
-- ----------------------------------------------------------------------------
-- 注意：SQLite 3.35.0+ 支持 ALTER TABLE DROP COLUMN
-- 如果是旧版本，需要使用表重建方式

-- 方式 A: SQLite 3.35.0+ (如果支持 DROP COLUMN)
-- ALTER TABLE samples_hourly DROP COLUMN gpu_details;

-- 方式 B: 表重建（兼容所有SQLite版本）
BEGIN TRANSACTION;

-- 1. 创建临时表（不含新字段）
CREATE TABLE samples_hourly_backup (
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

-- 2. 复制数据（排除 gpu_details）
INSERT INTO samples_hourly_backup 
    (id, server_id, ts, cpu_pct_avg, cpu_pct_max, 
     disk_used_pct, disk_used_bytes, disk_total_bytes,
     gpu_util_pct_avg, gpu_util_pct_max, gpu_mem_used_mb, gpu_mem_total_mb)
SELECT 
    id, server_id, ts, cpu_pct_avg, cpu_pct_max,
    disk_used_pct, disk_used_bytes, disk_total_bytes,
    gpu_util_pct_avg, gpu_util_pct_max, gpu_mem_used_mb, gpu_mem_total_mb
FROM samples_hourly;

-- 3. 删除原表
DROP TABLE samples_hourly;

-- 4. 重命名备份表
ALTER TABLE samples_hourly_backup RENAME TO samples_hourly;

-- 5. 重建索引
CREATE INDEX IF NOT EXISTS idx_samples_hourly_server_ts ON samples_hourly(server_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_samples_hourly_ts ON samples_hourly(ts);

COMMIT;

-- ----------------------------------------------------------------------------
-- Step 2: 回滚 servers 表（移除 proxy_config）
-- ----------------------------------------------------------------------------
BEGIN TRANSACTION;

-- 1. 创建临时表（不含新字段）
CREATE TABLE servers_backup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    host TEXT NOT NULL,
    agent_port INTEGER DEFAULT 9109,
    enabled INTEGER DEFAULT 1,
    services TEXT,
    token TEXT NOT NULL,
    last_seen_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 2. 复制数据（排除 proxy_config）
INSERT INTO servers_backup 
    (id, name, host, agent_port, enabled, services, token, last_seen_at, created_at)
SELECT 
    id, name, host, agent_port, enabled, services, token, last_seen_at, created_at
FROM servers;

-- 3. 删除原表
DROP TABLE servers;

-- 4. 重命名备份表
ALTER TABLE servers_backup RENAME TO servers;

-- 5. 重建索引
CREATE UNIQUE INDEX IF NOT EXISTS idx_servers_name ON servers(name);

COMMIT;

-- ----------------------------------------------------------------------------
-- Step 3: 删除迁移记录
-- ----------------------------------------------------------------------------
DELETE FROM schema_migrations WHERE version = '1.1.0';

-- ----------------------------------------------------------------------------
-- 回滚完成
-- ----------------------------------------------------------------------------
-- 验证命令：
-- sqlite3 monitor.db "PRAGMA table_info(servers);"
-- sqlite3 monitor.db "PRAGMA table_info(samples_hourly);"
-- sqlite3 monitor.db "SELECT * FROM schema_migrations;"
