"""
数据模型定义

包括：
- Pydantic 响应模型
- 内存缓存数据结构
- 全局状态管理
"""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field
import asyncio


# =============================================================================
# Pydantic 响应模型（用于 API 和数据验证）
# =============================================================================

class DiskInfo(BaseModel):
    """磁盘信息"""
    mount: str
    used_bytes: int
    total_bytes: int
    used_pct: float


class GPUInfo(BaseModel):
    """GPU 信息"""
    index: int
    name: Optional[str] = None  # GPU 型号名称（如 "NVIDIA A100"）
    util_pct: float
    mem_used_mb: int
    mem_total_mb: int
    temperature_c: Optional[float] = None  # GPU 温度（摄氏度）


class ServiceInfo(BaseModel):
    """服务状态信息"""
    name: str
    active_state: str
    sub_state: str


class AgentSnapshot(BaseModel):
    """Agent 快照（从 Agent 拉取的数据）"""
    node_id: str
    ts: str
    cpu_pct: Optional[float] = None
    disks: List[DiskInfo] = Field(default_factory=list)
    gpus: Optional[List[GPUInfo]] = None
    services: List[ServiceInfo] = Field(default_factory=list)


class LatestSnapshot(BaseModel):
    """最新快照（存储在内存中，供前端 5s 刷新）"""
    ts: str
    online: bool = True
    cpu_pct: Optional[float] = None
    disk_used_pct: Optional[float] = None
    disk_used_bytes: Optional[int] = None
    disk_total_bytes: Optional[int] = None
    
    # 多 GPU 支持
    gpus: Optional[List[GPUInfo]] = None  # 完整 GPU 数组
    gpu_count: int = 0  # GPU 数量
    
    # 向后兼容字段（聚合值）
    gpu_util_pct: Optional[float] = None  # 最高利用率（最忙的 GPU）
    gpu_util_pct_avg: Optional[float] = None  # 平均利用率
    gpu_mem_used_mb: Optional[int] = None  # 总显存使用（所有 GPU 之和）
    gpu_mem_total_mb: Optional[int] = None  # 总显存容量（所有 GPU 之和）
    
    services_failed_count: int = 0


class ServerResponse(BaseModel):
    """服务器响应模型（GET /api/servers）"""
    id: int
    name: str
    host: str
    agent_port: int = 9109
    token: Optional[str] = None  # 用于前端编辑时回填
    enabled: bool = True
    online: bool = False
    last_seen_at: Optional[str] = None
    latest: Optional[LatestSnapshot] = None


class ServerCreate(BaseModel):
    """创建服务器请求模型"""
    name: str
    host: str
    agent_port: int = 9109
    token: str
    services: List[str] = Field(default_factory=list)
    enabled: bool = True


class ServerUpdate(BaseModel):
    """更新服务器请求模型"""
    name: Optional[str] = None
    host: Optional[str] = None
    agent_port: Optional[int] = None
    token: Optional[str] = None
    services: Optional[List[str]] = None
    enabled: Optional[bool] = None


class TimeseriesPoint(BaseModel):
    """时序数据点"""
    ts: str
    value: Optional[float] = None


class TimeseriesResponse(BaseModel):
    """时序数据响应"""
    server_id: int
    metric: str
    agg: str
    data: List[TimeseriesPoint] = Field(default_factory=list)


class EventResponse(BaseModel):
    """事件响应模型"""
    id: int
    server_id: int
    server_name: str
    ts: str
    type: str
    message: Optional[str] = None


class HourlySampleResponse(BaseModel):
    """小时聚合样本响应（用于历史查询）"""
    id: int
    server_id: int
    server_name: str
    ts: str
    cpu_pct_avg: Optional[float] = None
    cpu_pct_max: Optional[float] = None
    disk_used_pct: Optional[float] = None
    disk_used_bytes: Optional[int] = None
    disk_total_bytes: Optional[int] = None
    gpu_util_pct_avg: Optional[float] = None
    gpu_util_pct_max: Optional[float] = None
    gpu_mem_used_mb: Optional[int] = None
    gpu_mem_total_mb: Optional[int] = None


class HourlyHistoryResponse(BaseModel):
    """历史数据分页响应"""
    total: int
    limit: int
    offset: int
    data: List[HourlySampleResponse] = Field(default_factory=list)


class ServiceCatalogItem(BaseModel):
    """服务发现项"""
    name: str
    active_state: str
    enabled: bool = True
    description: Optional[str] = None


class ProxyConfig(BaseModel):
    """代理转发配置（存储于 servers.proxy_config）"""

    enabled: bool = False
    server_listen_port: int
    center_proxy_port: int
    center_ssh_host: str
    center_ssh_port: int = 22
    center_ssh_user: str
    identity_file: str
    strict_host_key_checking: bool = True
    auto_start: bool = False


class ProxyStatus(BaseModel):
    """Agent 侧代理转发状态"""

    status: Literal["disabled", "stopped", "connecting", "connected", "error", "unknown"] = "unknown"
    pid: Optional[int] = None
    listen_port: Optional[int] = None
    target: Optional[str] = None
    last_error: Optional[str] = None
    connected_since: Optional[str] = None
    retry_count: int = 0


class ServerProxyResponse(BaseModel):
    """GET /api/servers/{id}/proxy 响应"""

    config: Optional[ProxyConfig] = None
    status: ProxyStatus


class ServerProxyUpdateRequest(BaseModel):
    """PUT /api/servers/{id}/proxy 请求"""

    config: Optional[ProxyConfig] = None
    action: Optional[Literal["start", "stop"]] = None


# =============================================================================
# 内存缓存（全局状态）
# =============================================================================

class MemoryCache:
    """
    内存缓存管理器
    
    管理：
    - server_latest: 每台服务器的最新快照（供前端 5s 刷新）
    - hourly_buffer: 每台服务器的小时缓冲区（用于整点聚合）
    - prev_state: 上一次状态（用于事件检测）
    """
    
    def __init__(self):
        # 服务器最新状态：{server_id: LatestSnapshot}
        self._server_latest: Dict[int, LatestSnapshot] = {}
        
        # 小时缓冲区：{server_id: [snapshot1, snapshot2, ...]}
        self._hourly_buffer: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        
        # 上一次状态（用于事件检测）：{server_id: {"online": bool, "services": {unit_name: active_state}}}
        self._prev_state: Dict[int, Dict[str, Any]] = {}
        
        # 线程安全锁
        self._lock = asyncio.Lock()
    
    async def get_latest(self, server_id: int) -> Optional[LatestSnapshot]:
        """获取服务器最新状态"""
        async with self._lock:
            return self._server_latest.get(server_id)
    
    async def set_latest(self, server_id: int, snapshot: LatestSnapshot):
        """设置服务器最新状态"""
        async with self._lock:
            self._server_latest[server_id] = snapshot
    
    async def get_all_latest(self) -> Dict[int, LatestSnapshot]:
        """获取所有服务器最新状态"""
        async with self._lock:
            return self._server_latest.copy()
    
    async def append_to_buffer(self, server_id: int, snapshot: Dict[str, Any]):
        """追加到小时缓冲区"""
        async with self._lock:
            self._hourly_buffer[server_id].append(snapshot)
    
    async def get_buffer(self, server_id: int) -> List[Dict[str, Any]]:
        """获取服务器的小时缓冲区"""
        async with self._lock:
            return list(self._hourly_buffer.get(server_id, []))
    
    async def get_all_buffers(self) -> Dict[int, List[Dict[str, Any]]]:
        """获取所有缓冲区"""
        async with self._lock:
            return {k: list(v) for k, v in self._hourly_buffer.items()}
    
    async def clear_all_buffers(self):
        """清空所有缓冲区"""
        async with self._lock:
            self._hourly_buffer.clear()
    
    async def get_prev_state(self, server_id: int) -> Dict[str, Any]:
        """获取上一次状态"""
        async with self._lock:
            return self._prev_state.get(server_id, {})
    
    async def set_prev_state(self, server_id: int, state: Dict[str, Any]):
        """设置上一次状态"""
        async with self._lock:
            self._prev_state[server_id] = state
    
    async def remove_server(self, server_id: int):
        """移除服务器相关数据"""
        async with self._lock:
            self._server_latest.pop(server_id, None)
            self._hourly_buffer.pop(server_id, None)
            self._prev_state.pop(server_id, None)


# 全局缓存实例
cache = MemoryCache()
