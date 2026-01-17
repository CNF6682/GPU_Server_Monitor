"""
服务器管理 API

提供服务器的 CRUD 操作和服务发现。
"""

import json
import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from ...config import get_config
from ...database import Database
from ...models import (
    ServerResponse, ServerCreate, ServerUpdate,
    LatestSnapshot, ServiceCatalogItem, cache
)
from ..dependencies import get_database, verify_admin_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/servers", tags=["servers"])


def parse_services(services_json: Optional[str]) -> List[str]:
    """解析服务列表 JSON"""
    if not services_json:
        return []
    try:
        return json.loads(services_json)
    except json.JSONDecodeError:
        return []


@router.get("", response_model=List[ServerResponse])
async def list_servers(db: Database = Depends(get_database)):
    """
    获取所有服务器及最新状态
    
    返回所有服务器列表，包含最新的缓存状态。
    """
    servers = db.get_all_servers()
    all_latest = await cache.get_all_latest()
    
    result = []
    for server in servers:
        server_id = server["id"]
        latest = all_latest.get(server_id)
        
        # 判断是否在线（12 秒阈值）
        online = latest.online if latest else False
        
        result.append(ServerResponse(
            id=server_id,
            name=server["name"],
            host=server["host"],
            agent_port=server["agent_port"],
            enabled=bool(server["enabled"]),
            online=online,
            last_seen_at=server.get("last_seen_at"),
            latest=latest
        ))
    
    return result


@router.get("/{server_id}", response_model=ServerResponse)
async def get_server(server_id: int, db: Database = Depends(get_database)):
    """获取单个服务器详情"""
    server = db.get_server_by_id(server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server {server_id} not found"
        )
    
    latest = await cache.get_latest(server_id)
    online = latest.online if latest else False
    
    return ServerResponse(
        id=server["id"],
        name=server["name"],
        host=server["host"],
        agent_port=server["agent_port"],
        enabled=bool(server["enabled"]),
        online=online,
        last_seen_at=server.get("last_seen_at"),
        latest=latest
    )


@router.post("", response_model=dict, dependencies=[Depends(verify_admin_token)])
async def create_server(data: ServerCreate, db: Database = Depends(get_database)):
    """
    添加服务器
    
    创建新的服务器配置，立即纳入采集循环。
    """
    # 检查名称是否已存在
    existing = db.get_server_by_name(data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Server name '{data.name}' already exists"
        )
    
    server_id = db.create_server(
        name=data.name,
        host=data.host,
        agent_port=data.agent_port,
        token=data.token,
        services=data.services,
        enabled=data.enabled
    )
    
    logger.info(f"Created server: {data.name} (id={server_id})")
    
    return {
        "id": server_id,
        "name": data.name,
        "created_at": db.get_server_by_id(server_id).get("created_at")
    }


@router.put("/{server_id}", dependencies=[Depends(verify_admin_token)])
async def update_server(
    server_id: int,
    data: ServerUpdate,
    db: Database = Depends(get_database)
):
    """更新服务器配置"""
    server = db.get_server_by_id(server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server {server_id} not found"
        )
    
    # 检查新名称是否与其他服务器冲突
    if data.name and data.name != server["name"]:
        existing = db.get_server_by_name(data.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Server name '{data.name}' already exists"
            )
    
    success = db.update_server(
        server_id=server_id,
        name=data.name,
        host=data.host,
        agent_port=data.agent_port,
        token=data.token,
        services=data.services,
        enabled=data.enabled
    )
    
    if success:
        logger.info(f"Updated server {server_id}")
    
    return {"success": success}


@router.delete("/{server_id}", dependencies=[Depends(verify_admin_token)])
async def delete_server(server_id: int, db: Database = Depends(get_database)):
    """删除服务器"""
    server = db.get_server_by_id(server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server {server_id} not found"
        )
    
    # 从缓存中移除
    await cache.remove_server(server_id)
    
    # 从数据库删除
    success = db.delete_server(server_id)
    
    if success:
        logger.info(f"Deleted server {server_id}")
    
    return {"success": success}


@router.get("/{server_id}/services/catalog", response_model=List[ServiceCatalogItem])
async def discover_services(server_id: int, db: Database = Depends(get_database)):
    """
    服务发现
    
    调用 Agent 的 /v1/services 端点，返回可选服务列表。
    """
    server = db.get_server_by_id(server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server {server_id} not found"
        )
    
    config = get_config()
    url = f"http://{server['host']}:{server['agent_port']}/v1/services"
    headers = {"Authorization": f"Bearer {server['token']}"}
    
    try:
        async with httpx.AsyncClient(timeout=config.collector.timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            services = response.json()
            
            return [
                ServiceCatalogItem(
                    name=svc.get("name", ""),
                    active_state=svc.get("active_state", "unknown"),
                    enabled=svc.get("enabled", True),
                    description=svc.get("description")
                )
                for svc in services
            ]
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to connect to agent: {e}"
        )
