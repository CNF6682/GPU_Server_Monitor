"""
5s 采集循环

每 5 秒拉取所有 Agent 数据，更新内存缓存，并触发事件检测。
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

import httpx

from .config import get_config
from .database import get_db
from .models import cache, LatestSnapshot
from .event_detector import detect_events

logger = logging.getLogger(__name__)


async def fetch_agent_snapshot(
    host: str,
    port: int,
    token: str,
    timeout: float = 2.0
) -> Dict[str, Any]:
    """
    拉取单个 Agent 的快照数据
    
    Args:
        host: Agent IP/域名
        port: Agent 端口
        token: Bearer Token
        timeout: 超时时间（秒）
    
    Returns:
        Agent 快照数据字典
    
    Raises:
        Exception: 拉取失败时抛出
    """
    url = f"http://{host}:{port}/v1/snapshot"
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def process_snapshot(server: Dict[str, Any], snapshot: Dict[str, Any]):
    """
    处理成功拉取的快照
    
    更新内存缓存、追加到缓冲区、检测事件。
    """
    server_id = server["id"]
    ts = snapshot.get("ts", datetime.utcnow().isoformat() + "Z")
    
    # 解析磁盘数据（取第一个挂载点）
    disks = snapshot.get("disks", [])
    disk_data = disks[0] if disks else {}
    
    # 解析 GPU 数据（取第一个 GPU）
    gpus = snapshot.get("gpus") or []
    gpu_data = gpus[0] if gpus else {}
    
    # 解析服务状态
    services = snapshot.get("services", [])
    failed_count = sum(1 for s in services if s.get("active_state") == "failed")
    
    # 构建最新快照
    latest = LatestSnapshot(
        ts=ts,
        online=True,
        cpu_pct=snapshot.get("cpu_pct"),
        disk_used_pct=disk_data.get("used_pct"),
        disk_used_bytes=disk_data.get("used_bytes"),
        disk_total_bytes=disk_data.get("total_bytes"),
        gpu_util_pct=gpu_data.get("util_pct"),
        gpu_mem_used_mb=gpu_data.get("mem_used_mb"),
        gpu_mem_total_mb=gpu_data.get("mem_total_mb"),
        services_failed_count=failed_count
    )
    
    # 更新内存缓存
    await cache.set_latest(server_id, latest)
    
    # 追加到小时缓冲区
    buffer_entry = {
        "ts": ts,
        "cpu_pct": snapshot.get("cpu_pct"),
        "disk_used_pct": disk_data.get("used_pct"),
        "disk_used_bytes": disk_data.get("used_bytes"),
        "disk_total_bytes": disk_data.get("total_bytes"),
        "gpu_util_pct": gpu_data.get("util_pct"),
        "gpu_mem_used_mb": gpu_data.get("mem_used_mb"),
        "gpu_mem_total_mb": gpu_data.get("mem_total_mb"),
    }
    await cache.append_to_buffer(server_id, buffer_entry)
    
    # 更新数据库中的 last_seen_at
    db = get_db()
    db.update_last_seen(server_id, ts)
    
    # 检测事件（在线状态变化、服务状态变化）
    await detect_events(server_id, True, services)


async def process_failure(server: Dict[str, Any], error: Exception):
    """
    处理拉取失败
    
    标记服务器离线，触发事件检测。
    """
    server_id = server["id"]
    server_name = server.get("name", f"server-{server_id}")
    
    logger.warning(f"Failed to fetch server {server_name}: {error}")
    
    # 获取上一次的状态，保留最后的指标值
    prev_latest = await cache.get_latest(server_id)
    
    if prev_latest:
        # 更新为离线状态，保留历史指标
        offline_latest = LatestSnapshot(
            ts=prev_latest.ts,
            online=False,
            cpu_pct=prev_latest.cpu_pct,
            disk_used_pct=prev_latest.disk_used_pct,
            disk_used_bytes=prev_latest.disk_used_bytes,
            disk_total_bytes=prev_latest.disk_total_bytes,
            gpu_util_pct=prev_latest.gpu_util_pct,
            gpu_mem_used_mb=prev_latest.gpu_mem_used_mb,
            gpu_mem_total_mb=prev_latest.gpu_mem_total_mb,
            services_failed_count=prev_latest.services_failed_count
        )
    else:
        # 首次就失败，创建空的离线状态
        offline_latest = LatestSnapshot(
            ts=datetime.utcnow().isoformat() + "Z",
            online=False
        )
    
    await cache.set_latest(server_id, offline_latest)
    
    # 检测事件（离线）
    await detect_events(server_id, False, [])


async def collect_single_server(server: Dict[str, Any], timeout: float):
    """采集单个服务器"""
    try:
        snapshot = await fetch_agent_snapshot(
            host=server["host"],
            port=server["agent_port"],
            token=server["token"],
            timeout=timeout
        )
        await process_snapshot(server, snapshot)
    except Exception as e:
        await process_failure(server, e)


async def run_collector():
    """
    运行采集循环
    
    每隔 interval 秒拉取所有启用的 Agent。
    """
    config = get_config()
    interval = config.collector.interval
    timeout = config.collector.timeout
    
    logger.info(f"Starting collector loop (interval={interval}s, timeout={timeout}s)")
    
    while True:
        try:
            db = get_db()
            servers = db.get_enabled_servers()
            
            if servers:
                # 并发拉取所有服务器
                tasks = [
                    collect_single_server(server, timeout)
                    for server in servers
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                logger.debug(f"Collected data from {len(servers)} servers")
            
        except Exception as e:
            logger.error(f"Collector loop error: {e}", exc_info=True)
        
        await asyncio.sleep(interval)
