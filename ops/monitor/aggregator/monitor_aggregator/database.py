"""
数据库操作抽象层

封装所有 SQLite 操作，提供 CRUD 接口。
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any

from .config import get_config


class Database:
    """数据库操作类"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径，不指定则从配置加载
        """
        if db_path is None:
            config = get_config()
            db_path = config.database.path
        
        self.db_path = Path(db_path)
        
        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def get_conn(self):
        """
        获取数据库连接（上下文管理器）
        
        使用方式：
            with db.get_conn() as conn:
                cursor = conn.execute("SELECT ...")
        """
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        # 启用外键约束
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # =========================================================================
    # 服务器操作
    # =========================================================================
    
    def get_all_servers(self) -> List[Dict[str, Any]]:
        """获取所有服务器"""
        with self.get_conn() as conn:
            cursor = conn.execute("""
                SELECT id, name, host, agent_port, enabled, services, token, last_seen_at, created_at
                FROM servers
                ORDER BY id
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_enabled_servers(self) -> List[Dict[str, Any]]:
        """获取所有启用的服务器"""
        with self.get_conn() as conn:
            cursor = conn.execute("""
                SELECT id, name, host, agent_port, enabled, services, token, last_seen_at, created_at
                FROM servers
                WHERE enabled = 1
                ORDER BY id
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_server_by_id(self, server_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取服务器"""
        with self.get_conn() as conn:
            cursor = conn.execute("""
                SELECT id, name, host, agent_port, enabled, services, token, last_seen_at, created_at
                FROM servers
                WHERE id = ?
            """, (server_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_server_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取服务器"""
        with self.get_conn() as conn:
            cursor = conn.execute("""
                SELECT id, name, host, agent_port, enabled, services, token, last_seen_at, created_at
                FROM servers
                WHERE name = ?
            """, (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create_server(
        self,
        name: str,
        host: str,
        token: str,
        agent_port: int = 9109,
        services: Optional[List[str]] = None,
        enabled: bool = True
    ) -> int:
        """
        创建服务器
        
        Returns:
            新创建的服务器 ID
        """
        services_json = json.dumps(services or [])
        with self.get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO servers (name, host, agent_port, enabled, services, token)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, host, agent_port, 1 if enabled else 0, services_json, token))
            return cursor.lastrowid
    
    def update_server(
        self,
        server_id: int,
        name: Optional[str] = None,
        host: Optional[str] = None,
        agent_port: Optional[int] = None,
        token: Optional[str] = None,
        services: Optional[List[str]] = None,
        enabled: Optional[bool] = None
    ) -> bool:
        """
        更新服务器
        
        Returns:
            是否更新成功
        """
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if host is not None:
            updates.append("host = ?")
            params.append(host)
        if agent_port is not None:
            updates.append("agent_port = ?")
            params.append(agent_port)
        if token is not None:
            updates.append("token = ?")
            params.append(token)
        if services is not None:
            updates.append("services = ?")
            params.append(json.dumps(services))
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)
        
        if not updates:
            return False
        
        params.append(server_id)
        sql = f"UPDATE servers SET {', '.join(updates)} WHERE id = ?"
        
        with self.get_conn() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount > 0
    
    def delete_server(self, server_id: int) -> bool:
        """
        删除服务器
        
        Returns:
            是否删除成功
        """
        with self.get_conn() as conn:
            cursor = conn.execute("DELETE FROM servers WHERE id = ?", (server_id,))
            return cursor.rowcount > 0
    
    def update_last_seen(self, server_id: int, ts: str):
        """更新服务器最后在线时间"""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE servers SET last_seen_at = ? WHERE id = ?",
                (ts, server_id)
            )
    
    # =========================================================================
    # 小时聚合样本操作
    # =========================================================================
    
    def save_hourly_sample(
        self,
        server_id: int,
        ts: str,
        cpu_pct_avg: Optional[float] = None,
        cpu_pct_max: Optional[float] = None,
        disk_used_pct: Optional[float] = None,
        disk_used_bytes: Optional[int] = None,
        disk_total_bytes: Optional[int] = None,
        gpu_util_pct_avg: Optional[float] = None,
        gpu_util_pct_max: Optional[float] = None,
        gpu_mem_used_mb: Optional[int] = None,
        gpu_mem_total_mb: Optional[int] = None
    ):
        """保存小时聚合样本"""
        with self.get_conn() as conn:
            conn.execute("""
                INSERT INTO samples_hourly (
                    server_id, ts,
                    cpu_pct_avg, cpu_pct_max,
                    disk_used_pct, disk_used_bytes, disk_total_bytes,
                    gpu_util_pct_avg, gpu_util_pct_max, gpu_mem_used_mb, gpu_mem_total_mb
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                server_id, ts,
                cpu_pct_avg, cpu_pct_max,
                disk_used_pct, disk_used_bytes, disk_total_bytes,
                gpu_util_pct_avg, gpu_util_pct_max, gpu_mem_used_mb, gpu_mem_total_mb
            ))
    
    def query_timeseries(
        self,
        server_id: int,
        metric: str,
        from_ts: str,
        to_ts: str,
        agg: str = "avg"
    ) -> List[Dict[str, Any]]:
        """
        查询时序数据
        
        Args:
            server_id: 服务器 ID
            metric: 指标名称（cpu_pct, disk_used_pct, gpu_util_pct）
            from_ts: 开始时间（ISO 8601）
            to_ts: 结束时间（ISO 8601）
            agg: 聚合类型（avg, max）
        
        Returns:
            [{ts: str, value: float}, ...]
        """
        # 映射 metric 到数据库列名
        column_map = {
            "cpu_pct": f"cpu_pct_{agg}",
            "disk_used_pct": "disk_used_pct",
            "gpu_util_pct": f"gpu_util_pct_{agg}"
        }
        
        column = column_map.get(metric)
        if not column:
            return []
        
        with self.get_conn() as conn:
            cursor = conn.execute(f"""
                SELECT ts, {column} as value
                FROM samples_hourly
                WHERE server_id = ? AND ts >= ? AND ts <= ?
                ORDER BY ts ASC
            """, (server_id, from_ts, to_ts))
            return [{"ts": row["ts"], "value": row["value"]} for row in cursor.fetchall()]
    
    # =========================================================================
    # 事件操作
    # =========================================================================
    
    def save_event(self, server_id: int, event_type: str, message: str) -> int:
        """
        保存事件（带 1 分钟去重）
        
        Returns:
            事件 ID（如果去重被跳过则返回 0）
        """
        now = datetime.utcnow()
        ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        one_minute_ago = (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        with self.get_conn() as conn:
            # 检查 1 分钟内是否有同类型事件
            cursor = conn.execute("""
                SELECT id FROM events
                WHERE server_id = ? AND type = ? AND ts > ?
                LIMIT 1
            """, (server_id, event_type, one_minute_ago))
            
            if cursor.fetchone():
                return 0  # 去重，跳过
            
            cursor = conn.execute("""
                INSERT INTO events (server_id, ts, type, message)
                VALUES (?, ?, ?, ?)
            """, (server_id, ts, event_type, message))
            return cursor.lastrowid
    
    def get_recent_events(self, limit: int = 200) -> List[Dict[str, Any]]:
        """获取最近事件（带服务器名称）"""
        with self.get_conn() as conn:
            cursor = conn.execute("""
                SELECT e.id, e.server_id, s.name as server_name, e.ts, e.type, e.message
                FROM events e
                JOIN servers s ON e.server_id = s.id
                ORDER BY e.ts DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    # =========================================================================
    # 数据清理
    # =========================================================================
    
    def cleanup_old_data(self, retention_days: int = 30):
        """
        清理过期数据
        
        Args:
            retention_days: 保留天数
        """
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        with self.get_conn() as conn:
            # 清理 samples_hourly
            conn.execute("DELETE FROM samples_hourly WHERE ts < ?", (cutoff,))
            
            # 清理 service_status
            conn.execute("DELETE FROM service_status WHERE ts < ?", (cutoff,))
            
            # 清理 events
            conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))


# 全局数据库实例（延迟加载）
_db: Optional[Database] = None


def get_db() -> Database:
    """获取全局数据库实例"""
    global _db
    if _db is None:
        _db = Database()
    return _db


def reset_db():
    """重置数据库实例（主要用于测试）"""
    global _db
    _db = None
