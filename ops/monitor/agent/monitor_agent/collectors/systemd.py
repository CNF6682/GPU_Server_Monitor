"""
systemd 服务采集器

查询 systemd 服务状态
"""

import asyncio
from typing import List, Dict


async def get_service_status(units: List[str]) -> List[Dict]:
    """
    采集 systemd 服务状态

    Args:
        units: 服务列表（如 ["nginx.service", "docker.service"]）

    Returns:
        服务状态列表，格式:
        [{"name": "nginx.service", "active_state": "active", "sub_state": "running"}]
    """
    if not units:
        return []

    # 并发查询所有服务
    tasks = [_query_single_service(unit) for unit in units]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 过滤掉失败的结果
    return [r for r in results if isinstance(r, dict)]


async def _query_single_service(unit: str) -> Dict:
    """
    查询单个服务状态

    Args:
        unit: 服务名称

    Returns:
        服务状态字典
    """
    try:
        cmd = f"systemctl show {unit} --property=ActiveState,SubState"

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            # 查询失败，返回未知状态
            return {
                "name": unit,
                "active_state": "unknown",
                "sub_state": "unknown"
            }

        # 解析输出
        # 格式:
        # ActiveState=active
        # SubState=running
        lines = stdout.decode().strip().split('\n')
        active_state = "unknown"
        sub_state = "unknown"

        for line in lines:
            if '=' in line:
                key, value = line.split('=', 1)
                if key == "ActiveState":
                    active_state = value
                elif key == "SubState":
                    sub_state = value

        return {
            "name": unit,
            "active_state": active_state,
            "sub_state": sub_state
        }

    except Exception:
        # 查询失败
        return {
            "name": unit,
            "active_state": "unknown",
            "sub_state": "unknown"
        }


async def discover_services() -> List[Dict]:
    """
    服务发现：列出所有可用的 systemd 服务

    Returns:
        服务列表，格式:
        [{"name": "nginx.service", "active_state": "active", "enabled": true, "description": "..."}]
    """
    try:
        # 列出所有服务
        cmd = "systemctl list-units --type=service --all --no-pager --no-legend"

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return []

        # 解析输出
        result = []
        lines = stdout.decode().strip().split('\n')

        for line in lines:
            if not line.strip():
                continue

            # 格式: UNIT LOAD ACTIVE SUB DESCRIPTION
            fields = line.split(None, 4)
            if len(fields) >= 5:
                unit_name = fields[0]
                active_state = fields[2]
                description = fields[4] if len(fields) > 4 else ""

                # 检查是否开机自启
                enabled = await _is_service_enabled(unit_name)

                result.append({
                    "name": unit_name,
                    "active_state": active_state,
                    "enabled": enabled,
                    "description": description
                })

        return result

    except Exception:
        return []


async def _is_service_enabled(unit: str) -> bool:
    """检查服务是否开机自启"""
    try:
        cmd = f"systemctl is-enabled {unit}"
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() == "enabled"
    except Exception:
        return False
