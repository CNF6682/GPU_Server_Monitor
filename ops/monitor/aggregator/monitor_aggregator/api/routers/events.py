"""
事件 API

提供事件查询。
"""

from typing import List

from fastapi import APIRouter, Depends, Query

from ...database import Database
from ...models import EventResponse
from ..dependencies import get_database

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=List[EventResponse])
async def list_events(
    limit: int = Query(200, ge=1, le=1000, description="返回数量限制"),
    db: Database = Depends(get_database)
):
    """
    获取最近事件
    
    返回最近的状态变化事件，按时间倒序排列。
    """
    events = db.get_recent_events(limit)
    
    return [
        EventResponse(
            id=e["id"],
            server_id=e["server_id"],
            server_name=e["server_name"],
            ts=e["ts"],
            type=e["type"],
            message=e.get("message")
        )
        for e in events
    ]
