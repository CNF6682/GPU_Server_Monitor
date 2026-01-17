"""
时间序列 API

提供历史数据查询。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...database import Database
from ...models import TimeseriesResponse, TimeseriesPoint
from ..dependencies import get_database

router = APIRouter(tags=["timeseries"])


@router.get("/api/servers/{server_id}/timeseries", response_model=TimeseriesResponse)
async def get_timeseries(
    server_id: int,
    metric: str = Query(..., description="指标名称：cpu_pct, disk_used_pct, gpu_util_pct"),
    from_ts: str = Query(..., alias="from", description="开始时间（ISO 8601）"),
    to_ts: str = Query(..., alias="to", description="结束时间（ISO 8601）"),
    agg: str = Query("avg", description="聚合类型：avg, max"),
    db: Database = Depends(get_database)
):
    """
    查询历史时间序列数据
    
    返回指定时间范围内的小时粒度数据。
    """
    # 验证服务器存在
    server = db.get_server_by_id(server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server {server_id} not found"
        )
    
    # 验证指标名称
    valid_metrics = ["cpu_pct", "disk_used_pct", "gpu_util_pct"]
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid metric. Must be one of: {valid_metrics}"
        )
    
    # 验证聚合类型
    valid_aggs = ["avg", "max"]
    if agg not in valid_aggs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid agg. Must be one of: {valid_aggs}"
        )
    
    # 查询数据
    data = db.query_timeseries(server_id, metric, from_ts, to_ts, agg)
    
    return TimeseriesResponse(
        server_id=server_id,
        metric=metric,
        agg=agg,
        data=[TimeseriesPoint(ts=d["ts"], value=d["value"]) for d in data]
    )
