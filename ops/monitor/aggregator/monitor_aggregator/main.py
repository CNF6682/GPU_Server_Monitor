"""
主程序入口

启动三个并发任务：
1. 5s 采集循环
2. 小时聚合任务
3. REST API 服务
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import uvicorn

from .config import get_config
from .database import get_db
from .collector import run_collector
from .aggregator import run_aggregator, run_cleanup
from .event_detector import check_all_servers_offline


def setup_logging():
    """配置日志"""
    config = get_config()
    
    # 日志格式
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # 获取日志级别
    level = getattr(logging, config.logging.level.upper(), logging.INFO)
    
    # 配置根日志
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # 如果配置了文件日志
    if config.logging.file:
        log_path = Path(config.logging.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(file_handler)
    
    # 降低第三方库日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def acquire_single_instance_lock(lock_path: Path):
    """
    防止误启动多个 Aggregator 实例（多实例会导致端口冲突/重复采集/SQLite 写入竞争）。

    通过文件锁实现：同一台机器同一路径下只能有一个进程持锁。
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # 使用二进制模式 + 固定锁定首字节，避免 Windows 上因文件指针位置不同而“锁到不同区域”。
    handle = open(lock_path, "a+b")
    try:
        handle.seek(0)
        if handle.tell() == 0 and handle.read(1) == b"":
            handle.write(b"0")
            handle.flush()
    except Exception:
        pass
    finally:
        try:
            handle.seek(0)
        except Exception:
            pass

    try:
        if os.name == "nt":
            import msvcrt  # type: ignore

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # type: ignore

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        handle.close()
        raise RuntimeError(f"Another Monitor Aggregator instance is already running (lock: {lock_path})") from e

    try:
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()).encode("utf-8"))
        handle.flush()
    except Exception:
        # 如果写 PID 失败不影响锁语义
        pass

    return handle


async def run_api_server():
    """运行 API 服务器"""
    from .api.app import create_app
    
    config = get_config()
    app = create_app()
    
    server_config = uvicorn.Config(
        app=app,
        host=config.api.host,
        port=config.api.port,
        log_level="info",
        access_log=False  # 我们用自己的日志
    )
    server = uvicorn.Server(server_config)
    await server.serve()


async def main():
    """主函数：启动所有任务"""
    logger = logging.getLogger(__name__)
    
    # 设置日志
    setup_logging()
    logger.info("=" * 60)
    logger.info("Monitor Aggregator v1.0.0")
    logger.info("=" * 60)
    
    # 加载配置
    config = get_config()
    logger.info(f"Config loaded: API={config.api.host}:{config.api.port}")
    logger.info(f"Database: {config.database.path}")

    # 单实例锁：避免重复启动
    lock_handle = None
    try:
        db_path = Path(config.database.path)
        lock_handle = acquire_single_instance_lock(db_path.parent / "monitor-aggregator.lock")
    except Exception as e:
        logger.error(str(e))
        return
    
    # 初始化数据库
    db = get_db()
    logger.info(f"Database initialized: {db.db_path}")
    
    # 初始化所有服务器状态
    await check_all_servers_offline()
    
    logger.info("Starting concurrent tasks...")
    
    # 启动三个并发任务
    try:
        await asyncio.gather(
            run_collector(),      # 5s 采集循环
            run_aggregator(),     # 小时聚合任务
            run_cleanup(),        # 数据清理任务
            run_api_server()      # REST API 服务
        )
    except asyncio.CancelledError:
        logger.info("Tasks cancelled, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        try:
            if lock_handle is not None:
                lock_handle.close()
        except Exception:
            pass


def cli():
    """命令行入口"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested, exiting...")
        sys.exit(0)


if __name__ == "__main__":
    cli()
