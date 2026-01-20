"""
FastAPI 应用配置

配置 CORS、静态文件托管、路由注册。
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..config import get_config
from .routers import servers, timeseries, events, history

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    创建 FastAPI 应用实例
    
    配置：
    - CORS 中间件
    - API 路由
    - 静态文件托管（前端）
    """
    config = get_config()
    
    app = FastAPI(
        title="Monitor Aggregator",
        description="服务器监控数据聚合和 API 服务",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json"
    )
    
    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api.cors_origins + ["*"],  # 开发环境允许所有
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册路由
    app.include_router(servers.router)
    app.include_router(timeseries.router)
    app.include_router(events.router)
    app.include_router(history.router)
    
    # 静态文件托管（前端）
    if config.frontend.enabled:
        frontend_path = Path(config.frontend.path)
        if frontend_path.exists():
            app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
            logger.info(f"Serving frontend from {frontend_path}")
        else:
            logger.warning(f"Frontend path not found: {frontend_path}")
    
    @app.on_event("startup")
    async def startup_event():
        logger.info("Monitor Aggregator starting up...")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Monitor Aggregator shutting down...")
    
    return app


# 默认应用实例
app = create_app()
