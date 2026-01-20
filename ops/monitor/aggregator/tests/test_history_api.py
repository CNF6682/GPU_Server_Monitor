"""
测试历史数据查询 API

测试 /api/history/hourly 端点的各种功能。
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from monitor_aggregator.api.app import create_app
from monitor_aggregator.api.dependencies import get_database
from monitor_aggregator.database import Database


@pytest.fixture
def client(db: Database):
    """创建测试客户端（使用临时数据库）"""
    app = create_app()

    async def _override_db():
        return db

    app.dependency_overrides[get_database] = _override_db
    return TestClient(app)


@pytest.fixture
def db(tmp_path):
    """创建临时测试数据库"""
    db_path = tmp_path / "test_monitor.db"
    db = Database(str(db_path))
    
    # 初始化数据库（需要先运行 schema.sql）
    # 这里简化处理，实际应该加载 schema.sql
    with db.get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS servers (
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
        """)
    
    return db


@pytest.fixture
def sample_data(db):
    """插入测试数据"""
    # 创建测试服务器
    server1_id = db.create_server("srv-01", "10.0.0.101", "token1")
    server2_id = db.create_server("srv-02", "10.0.0.102", "token2")
    
    # 插入测试样本数据
    base_time = datetime(2026, 1, 20, 10, 0, 0)
    for i in range(50):  # 创建 50 条样本
        ts = (base_time + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00:00Z")
        
        # 服务器 1 数据
        db.save_hourly_sample(
            server_id=server1_id,
            ts=ts,
            cpu_pct_avg=20.0 + i,
            cpu_pct_max=30.0 + i,
            disk_used_pct=50.0,
            disk_used_bytes=100000000,
            disk_total_bytes=200000000,
            gpu_util_pct_avg=40.0 + i,
            gpu_util_pct_max=50.0 + i,
            gpu_mem_used_mb=4096,
            gpu_mem_total_mb=8192
        )
        
        # 服务器 2 数据（每隔一个小时）
        if i % 2 == 0:
            db.save_hourly_sample(
                server_id=server2_id,
                ts=ts,
                cpu_pct_avg=30.0 + i,
                cpu_pct_max=40.0 + i,
                disk_used_pct=60.0,
                disk_used_bytes=150000000,
                disk_total_bytes=300000000
            )
    
    return {"server1_id": server1_id, "server2_id": server2_id}


class TestHistoryAPI:
    """历史数据查询 API 测试"""
    
    def test_basic_query(self, client, sample_data):
        """测试基本查询"""
        response = client.get("/api/history/hourly")
        assert response.status_code == 200
        
        data = response.json()
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "data" in data
        assert data["limit"] == 20  # 默认限制
        assert len(data["data"]) <= 20
    
    def test_pagination(self, client, sample_data):
        """测试分页功能"""
        # 第一页
        response1 = client.get("/api/history/hourly?limit=10&offset=0")
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["data"]) == 10
        assert data1["offset"] == 0
        
        # 第二页
        response2 = client.get("/api/history/hourly?limit=10&offset=10")
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["offset"] == 10
        
        # 确保数据不重复
        ids1 = {item["id"] for item in data1["data"]}
        ids2 = {item["id"] for item in data2["data"]}
        assert len(ids1.intersection(ids2)) == 0
    
    def test_server_filter(self, client, sample_data):
        """测试服务器筛选"""
        server1_id = sample_data["server1_id"]
        
        response = client.get(f"/api/history/hourly?server_ids={server1_id}&limit=100")
        assert response.status_code == 200
        
        data = response.json()
        # 所有结果应该只属于 server1
        for item in data["data"]:
            assert item["server_id"] == server1_id
    
    def test_multi_server_filter(self, client, sample_data):
        """测试多服务器筛选"""
        server1_id = sample_data["server1_id"]
        server2_id = sample_data["server2_id"]
        
        response = client.get(f"/api/history/hourly?server_ids={server1_id},{server2_id}&limit=100")
        assert response.status_code == 200
        
        data = response.json()
        server_ids = {item["server_id"] for item in data["data"]}
        assert server_ids <= {server1_id, server2_id}
    
    def test_time_range_filter(self, client, sample_data):
        """测试时间范围筛选"""
        from_ts = "2026-01-20T15:00:00Z"
        to_ts = "2026-01-20T20:00:00Z"
        
        response = client.get(f"/api/history/hourly?from={from_ts}&to={to_ts}&limit=100")
        assert response.status_code == 200
        
        data = response.json()
        # 验证所有结果在时间范围内
        for item in data["data"]:
            assert from_ts <= item["ts"] <= to_ts
    
    def test_sorting(self, client, sample_data):
        """测试排序功能"""
        # 按时间升序
        response_asc = client.get("/api/history/hourly?sort_by=ts&sort_order=asc&limit=10")
        assert response_asc.status_code == 200
        data_asc = response_asc.json()
        
        # 验证升序
        timestamps_asc = [item["ts"] for item in data_asc["data"]]
        assert timestamps_asc == sorted(timestamps_asc)
        
        # 按时间降序
        response_desc = client.get("/api/history/hourly?sort_by=ts&sort_order=desc&limit=10")
        assert response_desc.status_code == 200
        data_desc = response_desc.json()
        
        # 验证降序
        timestamps_desc = [item["ts"] for item in data_desc["data"]]
        assert timestamps_desc == sorted(timestamps_desc, reverse=True)
    
    def test_limit_boundary(self, client, sample_data):
        """测试限制边界"""
        # FastAPI Query 校验：超出范围返回 422
        response = client.get("/api/history/hourly?limit=2000")
        assert response.status_code == 422

        response = client.get("/api/history/hourly?limit=0")
        assert response.status_code == 422
    
    def test_empty_result(self, client, sample_data):
        """测试空结果"""
        # 查询未来时间
        from_ts = "2030-01-01T00:00:00Z"
        response = client.get(f"/api/history/hourly?from={from_ts}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["total"] == 0
        assert len(data["data"]) == 0
    
    def test_csv_export(self, client, sample_data):
        """测试 CSV 导出"""
        response = client.get("/api/history/hourly/export?limit=10")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        
        # 验证 CSV 内容
        csv_content = response.text
        assert "server_id" in csv_content
        assert "ts" in csv_content
        assert "cpu_pct_avg" in csv_content
