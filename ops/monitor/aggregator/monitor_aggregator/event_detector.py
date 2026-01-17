"""
事件检测模块

检测服务器状态变化（在线/离线、服务失败/恢复）并保存事件。
"""

import logging
from typing import Dict, List, Any, Optional

from .models import cache
from .database import get_db

logger = logging.getLogger(__name__)


async def detect_events(
    server_id: int,
    current_online: bool,
    current_services: Optional[List[Dict[str, Any]]] = None
):
    """
    检测状态变化并保存事件
    
    Args:
        server_id: 服务器 ID
        current_online: 当前是否在线
        current_services: 当前服务状态列表（可选）
    """
    events = []
    prev = await cache.get_prev_state(server_id)
    
    # 1. 在线状态变化检测
    prev_online = prev.get("online")
    
    if prev_online is True and current_online is False:
        events.append({
            "type": "server_down",
            "message": "Server went offline"
        })
        logger.warning(f"Server {server_id} went offline")
    elif prev_online is False and current_online is True:
        events.append({
            "type": "server_up",
            "message": "Server came back online"
        })
        logger.info(f"Server {server_id} came back online")
    
    # 2. 服务状态变化检测（仅当配置了服务监控时）
    if current_services:
        prev_services = prev.get("services", {})
        
        for svc in current_services:
            unit_name = svc.get("name", "")
            current_active = svc.get("active_state", "")
            prev_active = prev_services.get(unit_name)
            
            if prev_active == "active" and current_active == "failed":
                events.append({
                    "type": "service_failed",
                    "message": f"Service {unit_name} failed"
                })
                logger.warning(f"Service {unit_name} failed on server {server_id}")
            elif prev_active == "failed" and current_active == "active":
                events.append({
                    "type": "service_recovered",
                    "message": f"Service {unit_name} recovered"
                })
                logger.info(f"Service {unit_name} recovered on server {server_id}")
    
    # 3. 保存事件到数据库
    db = get_db()
    for event in events:
        event_id = db.save_event(server_id, event["type"], event["message"])
        if event_id:
            logger.debug(f"Saved event {event_id}: {event['type']} for server {server_id}")
    
    # 4. 更新状态缓存
    new_state = {
        "online": current_online,
        "services": {
            s.get("name", ""): s.get("active_state", "")
            for s in (current_services or [])
        }
    }
    await cache.set_prev_state(server_id, new_state)


async def check_all_servers_offline():
    """
    检查所有服务器是否离线（用于服务启动时初始化）
    
    在服务启动时调用，将所有服务器的初始状态设为 None（未知），
    避免首次拉取失败时误报 server_down 事件。
    """
    db = get_db()
    servers = db.get_enabled_servers()
    
    for server in servers:
        server_id = server["id"]
        # 设置初始状态为 None（未知），避免首次误报
        await cache.set_prev_state(server_id, {"online": None, "services": {}})
    
    logger.info(f"Initialized state for {len(servers)} servers")
