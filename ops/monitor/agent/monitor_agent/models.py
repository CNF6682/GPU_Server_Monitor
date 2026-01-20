"""
数据模型定义

使用 Pydantic 定义 API 响应数据结构
"""

from datetime import datetime
from typing import List, Optional, Dict, Literal, Any

from pydantic import BaseModel, Field


class DiskInfo(BaseModel):
    """磁盘信息"""
    mount: str = Field(..., description="挂载点")
    used_bytes: int = Field(..., description="已使用字节数")
    total_bytes: int = Field(..., description="总字节数")
    used_pct: float = Field(..., description="使用率百分比 (0-100)")


class GPUInfo(BaseModel):
    """GPU 信息"""
    index: int = Field(..., description="GPU 索引")
    name: str = Field(..., description="GPU 名称")
    util_pct: float = Field(..., description="GPU 使用率 (0-100)")
    mem_used_mb: int = Field(..., description="显存已使用 MB")
    mem_total_mb: int = Field(..., description="显存总量 MB")
    temperature_c: Optional[float] = Field(None, description="GPU 温度 (摄氏度)")


class ServiceInfo(BaseModel):
    """systemd 服务信息"""
    name: str = Field(..., description="服务名称")
    active_state: str = Field(..., description="激活状态: active|inactive|failed")
    sub_state: str = Field(..., description="子状态: running|exited|dead")


class ServiceDiscoveryInfo(BaseModel):
    """服务发现信息（扩展版）"""
    name: str = Field(..., description="服务名称")
    active_state: str = Field(..., description="激活状态")
    enabled: bool = Field(..., description="是否开机自启")
    description: str = Field(default="", description="服务描述")


class SnapshotResponse(BaseModel):
    """快照响应数据"""
    node_id: str = Field(..., description="节点 ID")
    ts: datetime = Field(..., description="采集时间戳")
    cpu_pct: Optional[float] = Field(None, description="CPU 使用率 (0-100)")
    disks: List[DiskInfo] = Field(default_factory=list, description="磁盘信息列表")
    gpus: Optional[List[GPUInfo]] = Field(None, description="GPU 信息列表")
    services: List[ServiceInfo] = Field(default_factory=list, description="服务状态列表")

    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")
        }


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="健康状态: ok|degraded|error")
    timestamp: datetime = Field(..., description="检查时间")
    checks: Dict[str, str] = Field(..., description="各组件检查结果")
    details: Dict[str, Optional[str]] = Field(..., description="详细信息")

    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")
        }


class ProxyStatusResponse(BaseModel):
    """代理转发状态响应"""

    status: Literal["disabled", "stopped", "connecting", "connected", "error"]
    pid: Optional[int] = None
    listen_port: Optional[int] = None
    target: Optional[str] = None
    last_error: Optional[str] = None
    connected_since: Optional[str] = None
    retry_count: int = 0


class ProxyStartRequest(BaseModel):
    """启动代理请求（可选携带配置覆盖）"""

    config: Optional[Dict[str, Any]] = None
