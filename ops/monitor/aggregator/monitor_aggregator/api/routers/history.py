"""
历史数据查询 API

提供历史数据的查询、筛选、分页和导出功能。
"""

import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from ...database import Database
from ...models import HourlyHistoryResponse, HourlySampleResponse
from ..dependencies import get_database

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/hourly", response_model=HourlyHistoryResponse)
async def get_hourly_history(
    server_id: Optional[int] = Query(None, description="单个服务器ID（兼容参数）"),
    server_ids: Optional[str] = Query(None, description="服务器ID列表（逗号分隔，如 '1,2,3'），为空则查询所有"),
    from_ts: Optional[str] = Query(None, alias="from", description="开始时间（ISO 8601）"),
    to_ts: Optional[str] = Query(None, alias="to", description="结束时间（ISO 8601）"),
    limit: int = Query(20, ge=1, le=1000, description="每页条数（1-1000）"),
    offset: int = Query(0, ge=0, description="偏移量"),
    sort_by: str = Query("ts", description="排序字段：ts, cpu_pct_avg, cpu_pct_max, disk_used_pct, gpu_util_pct_avg, gpu_util_pct_max, server_name"),
    sort_order: str = Query("desc", description="排序方向：asc, desc"),
    db: Database = Depends(get_database)
):
    """
    查询历史小时聚合数据
    
    支持：
    - 多服务器筛选
    - 时间范围筛选
    - 分页（每次最多返回 1000 条）
    - 多字段排序
    """
    # 解析服务器 ID 列表
    server_id_list = None
    if server_ids is None and server_id is not None:
        server_id_list = [server_id]
    if server_ids:
        try:
            server_id_list = [int(sid.strip()) for sid in server_ids.split(",") if sid.strip()]
        except ValueError:
            server_id_list = None
    
    # 查询数据
    data, total = db.query_hourly_history(
        server_ids=server_id_list,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    # 转换为响应模型
    samples = [HourlySampleResponse(**row) for row in data]
    
    return HourlyHistoryResponse(
        total=total,
        limit=limit,
        offset=offset,
        data=samples
    )


@router.get("/hourly/export")
async def export_hourly_history(
    server_id: Optional[int] = Query(None, description="单个服务器ID（兼容参数）"),
    server_ids: Optional[str] = Query(None, description="服务器ID列表（逗号分隔）"),
    from_ts: Optional[str] = Query(None, alias="from", description="开始时间（ISO 8601）"),
    to_ts: Optional[str] = Query(None, alias="to", description="结束时间（ISO 8601）"),
    sort_by: str = Query("ts", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    db: Database = Depends(get_database)
):
    """
    导出历史数据为 CSV
    
    注意：导出最多 1000 条记录。
    """
    # 解析服务器 ID 列表
    server_id_list = None
    if server_ids is None and server_id is not None:
        server_id_list = [server_id]
    if server_ids:
        try:
            server_id_list = [int(sid.strip()) for sid in server_ids.split(",") if sid.strip()]
        except ValueError:
            server_id_list = None
    
    # 查询数据（最多 1000 条）
    data, _ = db.query_hourly_history(
        server_ids=server_id_list,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=1000,
        offset=0,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    # 生成 CSV
    output = io.StringIO()
    if data:
        fieldnames = [
            "id", "server_id", "server_name", "ts",
            "cpu_pct_avg", "cpu_pct_max",
            "disk_used_pct", "disk_used_bytes", "disk_total_bytes",
            "gpu_util_pct_avg", "gpu_util_pct_max", "gpu_mem_used_mb", "gpu_mem_total_mb"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    
    # 返回 CSV 文件
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=history_export.csv"}
    )
