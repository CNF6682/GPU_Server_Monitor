"""
磁盘采集器

采集指定挂载点的磁盘使用情况
"""

import asyncio
from typing import List, Dict


async def get_disk_usage(mount_points: List[str]) -> List[Dict]:
    """
    采集磁盘使用率

    Args:
        mount_points: 挂载点列表（如 ["/", "/data"]）

    Returns:
        磁盘信息列表，格式:
        [{"mount": "/", "used_bytes": ..., "total_bytes": ..., "used_pct": ...}]
    """
    result = []

    for mount in mount_points:
        try:
            # 使用 psutil 获取磁盘使用情况
            import psutil
            usage = psutil.disk_usage(mount)

            result.append({
                "mount": mount,
                "used_bytes": usage.used,
                "total_bytes": usage.total,
                "used_pct": round(usage.percent, 2)
            })

        except ImportError:
            # 如果没有 psutil，使用 df 命令
            try:
                proc = await asyncio.create_subprocess_shell(
                    f"df -P {mount}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode == 0:
                    lines = stdout.decode().strip().split('\n')
                    if len(lines) >= 2:
                        # 解析 df 输出
                        # 格式: Filesystem 1024-blocks Used Available Capacity Mounted
                        fields = lines[1].split()
                        if len(fields) >= 5:
                            total_kb = int(fields[1])
                            used_kb = int(fields[2])
                            used_pct = float(fields[4].rstrip('%'))

                            result.append({
                                "mount": mount,
                                "used_bytes": used_kb * 1024,
                                "total_bytes": total_kb * 1024,
                                "used_pct": round(used_pct, 2)
                            })
            except Exception:
                # 单个挂载点失败，跳过
                pass

        except Exception:
            # 单个挂载点失败，跳过
            pass

    return result
