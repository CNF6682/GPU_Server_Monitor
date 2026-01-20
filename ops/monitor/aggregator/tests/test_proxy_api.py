"""
测试代理转发配置 API

覆盖：
- GET /api/servers/{id}/proxy 返回 config + status
- PUT /api/servers/{id}/proxy 保存配置并触发 action
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 添加项目路径到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor_aggregator.api.app import create_app
from monitor_aggregator.api.dependencies import get_database
from monitor_aggregator.database import Database
from monitor_aggregator.api.routers import servers as servers_router


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_monitor.db"
    db = Database(str(db_path))
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
                proxy_config TEXT,
                last_seen_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
    return db


@pytest.fixture
def app(db: Database):
    app = create_app()

    async def _override_db():
        return db

    app.dependency_overrides[get_database] = _override_db
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def server_id(db: Database):
    sid = db.create_server(name="srv-01", host="10.0.0.101", token="token1", agent_port=9109)
    db.set_proxy_config(sid, None)
    return sid


def test_get_proxy_returns_config_and_status(client: TestClient, server_id: int, monkeypatch):
    async def _fake_status(_server):
        return {"status": "connected", "pid": 123, "retry_count": 0}

    monkeypatch.setattr(servers_router, "fetch_agent_proxy_status", _fake_status)

    resp = client.get(f"/api/servers/{server_id}/proxy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["config"] is None
    assert data["status"]["status"] == "connected"
    assert data["status"]["pid"] == 123


def test_put_proxy_saves_and_triggers_start(client: TestClient, db: Database, server_id: int, monkeypatch):
    called = {"ok": False}

    async def _fake_action(_server, action, config_payload):
        assert action == "start"
        assert config_payload is not None
        assert config_payload.server_listen_port == 8080
        called["ok"] = True
        return {"status": "connecting"}

    async def _fake_status(_server):
        return {"status": "connected", "pid": 999, "retry_count": 0}

    monkeypatch.setattr(servers_router, "send_agent_proxy_action", _fake_action)
    monkeypatch.setattr(servers_router, "fetch_agent_proxy_status", _fake_status)

    payload = {
        "config": {
            "enabled": True,
            "server_listen_port": 8080,
            "center_proxy_port": 7879,
            "center_ssh_host": "192.168.1.100",
            "center_ssh_port": 22,
            "center_ssh_user": "dhga",
            "identity_file": "/home/monitor/.ssh/id_ed25519_monitor",
            "strict_host_key_checking": True,
            "auto_start": False,
        },
        "action": "start",
    }
    resp = client.put(f"/api/servers/{server_id}/proxy", json=payload)
    assert resp.status_code == 200
    assert called["ok"] is True

    stored = db.get_proxy_config(server_id)
    assert stored is not None and "center_ssh_host" in stored

    data = resp.json()
    assert data["config"]["enabled"] is True
    assert data["status"]["status"] == "connected"

