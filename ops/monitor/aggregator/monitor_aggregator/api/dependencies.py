"""
依赖注入模块

提供 FastAPI 依赖项。
"""

from typing import Optional
from fastapi import Header, HTTPException, status

from ..config import get_config
from ..database import get_db, Database


async def get_database() -> Database:
    """获取数据库实例"""
    return get_db()


async def verify_admin_token(x_admin_token: Optional[str] = Header(None)):
    """
    验证管理员 Token
    
    用于保护 POST/PUT/DELETE 操作。
    """
    config = get_config()
    expected_token = config.api.admin_token
    
    # 如果配置为默认值，跳过验证（开发环境）
    if expected_token == "CHANGE_ME_IN_PRODUCTION":
        return
    
    if x_admin_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token"
        )
