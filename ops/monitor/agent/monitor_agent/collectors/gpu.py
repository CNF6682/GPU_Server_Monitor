"""
GPU 采集器

通过 nvidia-smi 采集 NVIDIA GPU 使用情况
"""

import asyncio
from typing import Optional, List, Dict


async def get_gpu_stats() -> Optional[List[Dict]]:
    """
    采集 GPU 使用率、显存、名称和温度

    Returns:
        GPU 信息列表，格式:
        [{
            "index": 0,
            "name": "NVIDIA A100-SXM4-40GB",
            "util_pct": 56,
            "mem_used_mb": 2048,
            "mem_total_mb": 8192,
            "temperature_c": 75.0
        }]
        或 None（无 GPU 或驱动不可用）
    """
    try:
        # 执行 nvidia-smi 命令，增加 name 和 temperature.gpu
        cmd = (
            "nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu "
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
            if len(fields) >= 6:
                try:
                    gpu_info = {
                        "index": int(fields[0]),
                        "name": fields[1],
                        "util_pct": float(fields[2]),
                        "mem_used_mb": int(fields[3]),
                        "mem_total_mb": int(fields[4]),
                        "temperature_c": float(fields[5])
                    }
                    result.append(gpu_info)
                except (ValueError, IndexError) as e:
                    # 单卡解析失败不影响其他卡，跳过该行
                    continue

        return result if result else None

    except Exception:
        # 采集失败，返回 None
        return None
