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


def aggregate_gpu_metrics(gpus: Optional[list]) -> Dict[str, Any]:
    """
    聚合多 GPU 指标，生成兼容字段
    
    Args:
        gpus: GPU 数组（来自 Agent 的 gpus 字段）
    
    Returns:
        包含聚合指标的字典：
        - gpu_count: GPU 数量
        - gpu_util_pct: 最高利用率（最忙的 GPU）
        - gpu_util_pct_avg: 平均利用率
        - gpu_mem_used_mb: 总显存使用（所有 GPU 之和）
        - gpu_mem_total_mb: 总显存容量（所有 GPU 之和）
    """
    if not gpus:
        return {
            "gpu_count": 0,
            "gpu_util_pct": None,
            "gpu_util_pct_avg": None,
            "gpu_mem_used_mb": None,
            "gpu_mem_total_mb": None,
        }
    
    # 提取利用率列表（容错：跳过缺失数据）
    util_values = [g.get("util_pct") for g in gpus if g.get("util_pct") is not None]
    mem_used_values = [g.get("mem_used_mb") for g in gpus if g.get("mem_used_mb") is not None]
    mem_total_values = [g.get("mem_total_mb") for g in gpus if g.get("mem_total_mb") is not None]
    
    return {
        "gpu_count": len(gpus),
        "gpu_util_pct": max(util_values) if util_values else None,  # 最忙的 GPU
        "gpu_util_pct_avg": sum(util_values) / len(util_values) if util_values else None,
        "gpu_mem_used_mb": sum(mem_used_values) if mem_used_values else None,
        "gpu_mem_total_mb": sum(mem_total_values) if mem_total_values else None,
    }


async def process_snapshot(server: Dict[str, Any], snapshot: Dict[str, Any]):
    """
    \u5904\u7406\u6210\u529f\u62c9\u53d6\u7684\u5feb\u7167
    
    \u66f4\u65b0\u5185\u5b58\u7f13\u5b58\u3001\u8ffd\u52a0\u5230\u7f13\u51b2\u533a\u3001\u68c0\u6d4b\u4e8b\u4ef6\u3002
    """
    server_id = server["id"]
    ts = snapshot.get("ts", datetime.utcnow().isoformat() + "Z")
    
    # \u89e3\u6790\u78c1\u76d8\u6570\u636e\uff08\u53d6\u7b2c\u4e00\u4e2a\u6302\u8f7d\u70b9\uff09
    disks = snapshot.get("disks", [])
    disk_data = disks[0] if disks else {}
    
    # \u89e3\u6790 GPU \u6570\u636e\uff08\u4fdd\u7559\u5b8c\u6574\u6570\u7ec4 + \u8ba1\u7b97\u805a\u5408\u503c\uff09
    gpus = snapshot.get("gpus") or []
    gpu_agg = aggregate_gpu_metrics(gpus)
    
    # \u89e3\u6790\u670d\u52a1\u72b6\u6001
    services = snapshot.get("services", [])
    failed_count = sum(1 for s in services if s.get("active_state") == "failed")
    
    # \u6784\u5efa\u6700\u65b0\u5feb\u7167
    latest = LatestSnapshot(
        ts=ts,
        online=True,
        cpu_pct=snapshot.get("cpu_pct"),
        disk_used_pct=disk_data.get("used_pct"),
        disk_used_bytes=disk_data.get("used_bytes"),
        disk_total_bytes=disk_data.get("total_bytes"),
        # \u591a GPU \u652f\u6301
        gpus=gpus if gpus else None,
        gpu_count=gpu_agg["gpu_count"],
        # \u805a\u5408\u5b57\u6bb5\uff08\u5411\u540e\u517c\u5bb9\uff09
        gpu_util_pct=gpu_agg["gpu_util_pct"],
        gpu_util_pct_avg=gpu_agg["gpu_util_pct_avg"],
        gpu_mem_used_mb=gpu_agg["gpu_mem_used_mb"],
        gpu_mem_total_mb=gpu_agg["gpu_mem_total_mb"],
        services_failed_count=failed_count
    )
    
    # \u66f4\u65b0\u5185\u5b58\u7f13\u5b58
    await cache.set_latest(server_id, latest)
    
    # \u8ffd\u52a0\u5230\u5c0f\u65f6\u7f13\u51b2\u533a\uff08\u4fdd\u7559\u805a\u5408\u6307\u6807\u7528\u4e8e\u5c0f\u65f6\u8bb0\u5f55\uff09
    buffer_entry = {
        "ts": ts,
        "cpu_pct": snapshot.get("cpu_pct"),
        "disk_used_pct": disk_data.get("used_pct"),
        "disk_used_bytes": disk_data.get("used_bytes"),
        "disk_total_bytes": disk_data.get("total_bytes"),
        # \u4f7f\u7528\u805a\u5408\u503c\u5b58\u50a8\u5230\u5c0f\u65f6\u8bb0\u5f55
        "gpu_util_pct": gpu_agg["gpu_util_pct"],
        "gpu_mem_used_mb": gpu_agg["gpu_mem_used_mb"],
        "gpu_mem_total_mb": gpu_agg["gpu_mem_total_mb"],
    }
    await cache.append_to_buffer(server_id, buffer_entry)
    
    # \u66f4\u65b0\u6570\u636e\u5e93\u4e2d\u7684 last_seen_at
    db = get_db()
    db.update_last_seen(server_id, ts)
    
    # \u68c0\u6d4b\u4e8b\u4ef6\uff08\u5728\u7ebf\u72b6\u6001\u53d8\u5316\u3001\u670d\u52a1\u72b6\u6001\u53d8\u5316\uff09
    await detect_events(server_id, True, services)


async def process_failure(server: Dict[str, Any], error: Exception):
    """
    \u5904\u7406\u62c9\u53d6\u5931\u8d25
    
    \u6807\u8bb0\u670d\u52a1\u5668\u79bb\u7ebf\uff0c\u89e6\u53d1\u4e8b\u4ef6\u68c0\u6d4b\u3002
    """
    server_id = server["id"]
    server_name = server.get("name", f"server-{server_id}")
    
    logger.warning(f"Failed to fetch server {server_name}: {error}")
    
    # \u83b7\u53d6\u4e0a\u4e00\u6b21\u7684\u72b6\u6001\uff0c\u4fdd\u7559\u6700\u540e\u7684\u6307\u6807\u503c
    prev_latest = await cache.get_latest(server_id)
    
    if prev_latest:
        # \u66f4\u65b0\u4e3a\u79bb\u7ebf\u72b6\u6001\uff0c\u4fdd\u7559\u5386\u53f2\u6307\u6807
        offline_latest = LatestSnapshot(
            ts=prev_latest.ts,
            online=False,
            cpu_pct=prev_latest.cpu_pct,
            disk_used_pct=prev_latest.disk_used_pct,
            disk_used_bytes=prev_latest.disk_used_bytes,
            disk_total_bytes=prev_latest.disk_total_bytes,
            # \u4fdd\u7559 GPU \u4fe1\u606f
            gpus=prev_latest.gpus,
            gpu_count=prev_latest.gpu_count,
            gpu_util_pct=prev_latest.gpu_util_pct,
            gpu_util_pct_avg=prev_latest.gpu_util_pct_avg,
            gpu_mem_used_mb=prev_latest.gpu_mem_used_mb,
            gpu_mem_total_mb=prev_latest.gpu_mem_total_mb,
            services_failed_count=prev_latest.services_failed_count
        )
    else:
        # \u9996\u6b21\u5c31\u5931\u8d25\uff0c\u521b\u5efa\u7a7a\u7684\u79bb\u7ebf\u72b6\u6001
        offline_latest = LatestSnapshot(
            ts=datetime.utcnow().isoformat() + "Z",
            online=False
        )
    
    await cache.set_latest(server_id, offline_latest)
    
    # \u68c0\u6d4b\u4e8b\u4ef6\uff08\u79bb\u7ebf\uff09
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
