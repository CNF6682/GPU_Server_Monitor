"""
CPU 采集器

通过读取 /proc/stat 计算 CPU 使用率
"""

import asyncio
from typing import Optional


# 全局变量：保存上一次采样数据
_last_cpu_stats = None


async def get_cpu_percent() -> Optional[float]:
    """
    采集 CPU 使用率

    实现方式：读取 /proc/stat 两次，计算 delta

    Returns:
        0~100 的浮点数，首次调用返回 None（需要两次采样）
    """
    global _last_cpu_stats

    try:
        # 读取 /proc/stat
        with open("/proc/stat", "r") as f:
            line = f.readline()

        # 解析第一行（总 CPU 统计）
        # 格式: cpu  user nice system idle iowait irq softirq steal guest guest_nice
        fields = line.split()
        if fields[0] != "cpu":
            return None

        # 提取各项时间值
        values = [int(x) for x in fields[1:]]
        total = sum(values)
        idle = values[3]  # idle 是第 4 个字段

        # 首次调用，保存数据并返回 None
        if _last_cpu_stats is None:
            _last_cpu_stats = (total, idle)
            return None

        # 计算 delta
        last_total, last_idle = _last_cpu_stats
        total_delta = total - last_total
        idle_delta = idle - last_idle

        # 更新缓存
        _last_cpu_stats = (total, idle)

        # 计算使用率
        if total_delta == 0:
            return 0.0

        cpu_pct = (total_delta - idle_delta) / total_delta * 100.0
        return round(cpu_pct, 2)

    except Exception as e:
        # 采集失败，返回 None
        return None
