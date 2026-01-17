"""
GPU 采集器

通过 nvidia-smi 采集 NVIDIA GPU 使用情况
"""

import asyncio
from typing import Optional, List, Dict


async def get_gpu_stats() -> Optional[List[Dict]]:
    """
    采集 GPU 使用率和显存

    Returns:
        GPU 信息列表，格式:
        [{"index": 0, "util_pct": 56, "mem_used_mb": 2048, "mem_total_mb": 8192}]
        或 None（无 GPU 或驱动不可用）
    """
    try:
        # 执行 nvidia-smi 命令
        cmd = (
            "nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total "
            "--format=csv,noheader,nounits"
        )

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            # nvidia-smi 执行失败（无驱动或无 GPU）
            return None

        # 解析 CSV 输出
        result = []
        lines = stdout.decode().strip().split('\n')

        for line in lines:
            if not line.strip():
                continue

            fields = [x.strip() for x in line.split(',')]
            if len(fields) >= 4:
                try:
                    result.append({
                        "index": int(fields[0]),
                        "util_pct": float(fields[1]),
                        "mem_used_mb": int(fields[2]),
                        "mem_total_mb": int(fields[3])
                    })
                except (ValueError, IndexError):
                    # 解析失败，跳过该行
                    continue

        return result if result else None

    except Exception:
        # 采集失败，返回 None
        return None
