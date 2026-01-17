-- ============================================================================
-- 监控系统数据库初始化脚本
-- 
-- 数据库: SQLite
-- 版本: 1.0.0
-- 说明: 此脚本支持幂等执行（可多次运行不会报错）
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 服务器配置表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,                    -- 服务器显示名称（唯一）
    host TEXT NOT NULL,                           -- IP 或域名
    agent_port INTEGER DEFAULT 9109,              -- Agent 端口
    enabled INTEGER DEFAULT 1,                    -- 1=启用, 0=禁用
    services TEXT,                                -- JSON 数组：需监控的 systemd 服务列表
    token TEXT NOT NULL,                          -- Bearer Token（与 Agent 共享）
    last_seen_at TEXT,                            -- 最后在线时间（ISO 8601 格式）
    created_at TEXT DEFAULT CURRENT_TIMESTAMP     -- 创建时间
);

-- 唯一索引：服务器名称
CREATE UNIQUE INDEX IF NOT EXISTS idx_servers_name ON servers(name);

-- ----------------------------------------------------------------------------
-- 小时聚合历史数据表
-- 核心时序表：每台服务器每小时保存 1 条聚合数据
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS samples_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,                   -- 关联 servers.id
    ts TEXT NOT NULL,                             -- 整点时间戳（如 "2026-01-17 10:00:00"）
    
    -- CPU 指标（0~100 浮点数）
    cpu_pct_avg REAL,                             -- 过去 1 小时平均 CPU 使用率
    cpu_pct_max REAL,                             -- 过去 1 小时峰值 CPU 使用率
    
    -- 磁盘指标（整点快照值）
    disk_used_pct REAL,                           -- 磁盘使用率百分比
    disk_used_bytes INTEGER,                      -- 已用字节数
    disk_total_bytes INTEGER,                     -- 总字节数
    
    -- GPU 指标（nullable，无 GPU 时为空）
    gpu_util_pct_avg REAL,                        -- 过去 1 小时平均 GPU 使用率
    gpu_util_pct_max REAL,                        -- 过去 1 小时峰值 GPU 使用率
    gpu_mem_used_mb INTEGER,                      -- GPU 显存已用（MB）
    gpu_mem_total_mb INTEGER,                     -- GPU 显存总量（MB）
    
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- 联合索引：按服务器和时间查询（降序，最新数据优先）
CREATE INDEX IF NOT EXISTS idx_samples_hourly_server_ts ON samples_hourly(server_id, ts DESC);

-- 时间索引：用于清理过期数据
CREATE INDEX IF NOT EXISTS idx_samples_hourly_ts ON samples_hourly(ts);

-- ----------------------------------------------------------------------------
-- 服务状态表
-- 仅当 servers.services 非空时才写入
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS service_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,                   -- 关联 servers.id
    ts TEXT NOT NULL,                             -- 采集时间
    unit_name TEXT NOT NULL,                      -- systemd 服务名称（如 nginx.service）
    active_state TEXT,                            -- 状态：active/inactive/failed
    sub_state TEXT,                               -- 子状态：running/exited/dead
    
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- 联合索引：按服务器和时间查询
CREATE INDEX IF NOT EXISTS idx_service_status_server_ts ON service_status(server_id, ts DESC);

-- ----------------------------------------------------------------------------
-- 事件表
-- 记录状态变化事件（掉线/恢复、服务失败/恢复等）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,                   -- 关联 servers.id
    ts TEXT NOT NULL,                             -- 事件时间
    type TEXT NOT NULL,                           -- 事件类型：server_down|server_up|service_failed|service_recovered
    message TEXT,                                 -- 事件消息
    
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- 时间索引：按时间查询最近事件
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);

-- 联合索引：按服务器和类型查询
CREATE INDEX IF NOT EXISTS idx_events_server_type ON events(server_id, type);

-- ----------------------------------------------------------------------------
-- 数据库配置
-- ----------------------------------------------------------------------------

-- 启用 WAL 模式（Write-Ahead Logging）
-- 优点：写操作不阻塞读操作，提高并发性能
PRAGMA journal_mode=WAL;

-- ----------------------------------------------------------------------------
-- 初始化完成
-- ----------------------------------------------------------------------------
