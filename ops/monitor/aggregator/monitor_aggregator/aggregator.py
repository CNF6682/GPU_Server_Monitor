"""
小时聚合任务

每小时整点触发，将缓冲区数据聚合后入库。
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from .config import get_config
from .database import get_db
from .models import cache

logger = logging.getLogger(__name__)


def calculate_aggregation(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    计算聚合指标
    
    Args:
        snapshots: 一小时内的快照列表
    
    Returns:
        聚合后的指标字典
    """
    if not snapshots:
        return {}
    
    # CPU 聚合（avg + max）
    cpu_values = [s.get("cpu_pct") for s in snapshots if s.get("cpu_pct") is not None]
    cpu_avg = sum(cpu_values) / len(cpu_values) if cpu_values else None
    cpu_max = max(cpu_values) if cpu_values else None
    
    # GPU 聚合（avg + max）
    gpu_values = [s.get("gpu_util_pct") for s in snapshots if s.get("gpu_util_pct") is not None]
    gpu_avg = sum(gpu_values) / len(gpu_values) if gpu_values else None
    gpu_max = max(gpu_values) if gpu_values else None
    
    # 磁盘取最后一个快照值（变化慢）
    last = snapshots[-1]
    
    # GPU 显存也取最后快照
    gpu_mem_used = None
    gpu_mem_total = None
    for s in reversed(snapshots):
        if s.get("gpu_mem_used_mb") is not None:
            gpu_mem_used = s.get("gpu_mem_used_mb")
            gpu_mem_total = s.get("gpu_mem_total_mb")
            break
    
    return {
        "cpu_pct_avg": round(cpu_avg, 2) if cpu_avg is not None else None,
        "cpu_pct_max": round(cpu_max, 2) if cpu_max is not None else None,
        "disk_used_pct": last.get("disk_used_pct"),
        "disk_used_bytes": last.get("disk_used_bytes"),
        "disk_total_bytes": last.get("disk_total_bytes"),
        "gpu_util_pct_avg": round(gpu_avg, 2) if gpu_avg is not None else None,
        "gpu_util_pct_max": round(gpu_max, 2) if gpu_max is not None else None,
        "gpu_mem_used_mb": gpu_mem_used,
        "gpu_mem_total_mb": gpu_mem_total,
    }


async def aggregate_and_save(hour_ts: str):
    """
    聚合所有服务器的缓冲数据并入库
    
    Args:
        hour_ts: 整点时间戳（如 "2026-01-17T10:00:00Z"）
    """
    db = get_db()
    buffers = await cache.get_all_buffers()
    
    saved_count = 0
    for server_id, snapshots in buffers.items():
        if not snapshots:
            continue
        
        agg = calculate_aggregation(snapshots)
        
        db.save_hourly_sample(
            server_id=server_id,
            ts=hour_ts,
            cpu_pct_avg=agg.get("cpu_pct_avg"),
            cpu_pct_max=agg.get("cpu_pct_max"),
            disk_used_pct=agg.get("disk_used_pct"),
            disk_used_bytes=agg.get("disk_used_bytes"),
            disk_total_bytes=agg.get("disk_total_bytes"),
            gpu_util_pct_avg=agg.get("gpu_util_pct_avg"),
            gpu_util_pct_max=agg.get("gpu_util_pct_max"),
            gpu_mem_used_mb=agg.get("gpu_mem_used_mb"),
            gpu_mem_total_mb=agg.get("gpu_mem_total_mb"),
        )
        saved_count += 1
        logger.debug(f"Saved hourly sample for server {server_id}: {agg}")
    
    # 清空缓冲区
    await cache.clear_all_buffers()
    
    logger.info(f"Aggregation completed: saved {saved_count} samples for hour {hour_ts}")


async def run_aggregator():
    """
    运行小时聚合任务
    
    等到下一个整点，然后执行聚合并写入数据库。
    """
    config = get_config()
    
    logger.info("Starting aggregator task")
    
    while True:
        try:
            now = datetime.utcnow()
            
            # 计算下一个整点
            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            wait_seconds = (next_hour - now).total_seconds()
            
            logger.info(f"Next aggregation at {next_hour.isoformat()}Z (in {wait_seconds:.0f}s)")
            
            # 等待到整点
            await asyncio.sleep(wait_seconds)
            
            # 执行聚合
            hour_ts = next_hour.strftime("%Y-%m-%dT%H:00:00Z")
            await aggregate_and_save(hour_ts)
            
        except asyncio.CancelledError:
            logger.info("Aggregator task cancelled")
            raise
        except Exception as e:
            logger.error(f"Aggregator error: {e}", exc_info=True)
            # 出错后等待一分钟再重试
            await asyncio.sleep(60)


async def run_cleanup():
    """
    运行数据清理任务
    
    每天在指定时间清理过期数据。
    """
    config = get_config()
    cleanup_hour = config.retention.cleanup_hour
    retention_days = config.retention.days
    
    logger.info(f"Starting cleanup task (hour={cleanup_hour}, retention={retention_days}d)")
    
    while True:
        try:
            now = datetime.utcnow()
            
            # 计算下次清理时间
            if now.hour >= cleanup_hour:
                # 今天的清理时间已过，等明天
                next_cleanup = (now + timedelta(days=1)).replace(
                    hour=cleanup_hour, minute=0, second=0, microsecond=0
                )
            else:
                # 今天还没到清理时间
                next_cleanup = now.replace(
                    hour=cleanup_hour, minute=0, second=0, microsecond=0
                )
            
            wait_seconds = (next_cleanup - now).total_seconds()
            logger.info(f"Next cleanup at {next_cleanup.isoformat()}Z (in {wait_seconds:.0f}s)")
            
            await asyncio.sleep(wait_seconds)
            
            # 执行清理
            db = get_db()
            db.cleanup_old_data(retention_days)
            logger.info(f"Cleanup completed: removed data older than {retention_days} days")
            
        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled")
            raise
        except Exception as e:
            logger.error(f"Cleanup error: {e}", exc_info=True)
            await asyncio.sleep(3600)  # 出错后等 1 小时
