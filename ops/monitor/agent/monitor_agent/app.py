"""
FastAPI 应用入口

提供 HTTP 接口供中心节点拉取数据
"""

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import JSONResponse

from monitor_agent.config import get_config, AgentConfig
from monitor_agent.models import (
    SnapshotResponse,
    HealthResponse,
    ServiceDiscoveryInfo,
    DiskInfo,
    GPUInfo,
    ServiceInfo,
)
from monitor_agent.collectors import (
    get_cpu_percent,
    get_disk_usage,
    get_gpu_stats,
    get_service_status,
)
from monitor_agent.collectors.systemd import discover_services


# 创建 FastAPI 应用
app = FastAPI(
    title="Monitor Agent",
    version="1.0.0",
    description="Linux 服务器监控代理"
)


def verify_token(authorization: Optional[str] = Header(None)) -> bool:
    """
    验证 Token

    Args:
        authorization: Authorization 头，格式为 "Bearer <token>"

    Returns:
        验证是否通过

    Raises:
        HTTPException: Token 无效时抛出 401 错误
    """
    config = get_config()

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # 解析 Bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = parts[1]
    if token != config.token:
        raise HTTPException(status_code=401, detail="Invalid token")

    return True


@app.get("/v1/snapshot", response_model=SnapshotResponse)
async def get_snapshot(authorized: bool = Depends(verify_token)):
    """
    获取系统快照数据

    返回 CPU、磁盘、GPU、服务状态等信息
    """
    config = get_config()

    # 并发调用所有采集器
    cpu_task = get_cpu_percent()
    disk_task = get_disk_usage(config.disks)
    gpu_task = get_gpu_stats() if config.gpu != "off" else None
    service_task = get_service_status(config.services_allowlist)

    # 等待所有任务完成
    results = await asyncio.gather(
        cpu_task,
        disk_task,
        gpu_task if gpu_task else asyncio.sleep(0),
        service_task,
        return_exceptions=True
    )

    cpu_pct = results[0] if not isinstance(results[0], Exception) else None
    disks = results[1] if not isinstance(results[1], Exception) else []
    gpus = results[2] if gpu_task and not isinstance(results[2], Exception) else None
    services = results[3] if not isinstance(results[3], Exception) else []

    # 构造响应
    return SnapshotResponse(
        node_id=config.node_id,
        ts=datetime.utcnow(),
        cpu_pct=cpu_pct,
        disks=[DiskInfo(**d) for d in disks],
        gpus=[GPUInfo(**g) for g in gpus] if gpus else None,
        services=[ServiceInfo(**s) for s in services]
    )


@app.get("/v1/health", response_model=HealthResponse)
async def get_health():
    """
    健康检查端点

    测试各采集器是否正常工作
    """
    config = get_config()
    checks = {}
    details = {}
    overall_status = "ok"

    # 检查 CPU 采集器
    try:
        cpu_result = await get_cpu_percent()
        checks["cpu"] = "ok"
        details["cpu"] = None
    except Exception as e:
        checks["cpu"] = "error"
        details["cpu"] = str(e)
        overall_status = "degraded"

    # 检查磁盘采集器
    try:
        disk_result = await get_disk_usage(config.disks)
        if disk_result:
            checks["disk"] = "ok"
            details["disk"] = None
        else:
            checks["disk"] = "degraded"
            details["disk"] = "No disk data available"
            overall_status = "degraded"
    except Exception as e:
        checks["disk"] = "error"
        details["disk"] = str(e)
        overall_status = "degraded"

    # 检查 GPU 采集器
    if config.gpu != "off":
        try:
            gpu_result = await get_gpu_stats()
            if gpu_result:
                checks["gpu"] = "ok"
                details["gpu"] = f"NVIDIA driver available, {len(gpu_result)} GPU(s) detected"
            else:
                checks["gpu"] = "degraded"
                details["gpu"] = "GPU not available or driver not installed"
                overall_status = "degraded"
        except Exception as e:
            checks["gpu"] = "error"
            details["gpu"] = str(e)
            overall_status = "degraded"
    else:
        checks["gpu"] = "disabled"
        details["gpu"] = "GPU monitoring disabled in config"

    # 检查 systemd 采集器
    try:
        if config.services_allowlist:
            service_result = await get_service_status(config.services_allowlist[:1])
            checks["systemd"] = "ok"
            details["systemd"] = None
        else:
            checks["systemd"] = "ok"
            details["systemd"] = "No services configured"
    except Exception as e:
        checks["systemd"] = "error"
        details["systemd"] = str(e)
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        checks=checks,
        details=details
    )


@app.get("/v1/services", response_model=list[ServiceDiscoveryInfo])
async def list_services(authorized: bool = Depends(verify_token)):
    """
    服务发现端点

    返回可供监控的 systemd 服务列表
    """
    try:
        services = await discover_services()
        return [ServiceDiscoveryInfo(**s) for s in services]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to discover services: {str(e)}")
