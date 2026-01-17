"""
配置加载模块

从 config.yaml 加载配置，支持 Pydantic 验证和环境变量覆盖。
"""

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseModel):
    """数据库配置"""
    path: str = "ops/monitor/data/monitor.db"
    pool_size: int = 5
    timeout: int = 30


class APIConfig(BaseModel):
    """API 服务配置"""
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: List[str] = ["http://localhost:8080", "http://127.0.0.1:8080"]
    admin_token: str = "CHANGE_ME_IN_PRODUCTION"


class FrontendConfig(BaseModel):
    """前端配置"""
    path: str = "ops/monitor/frontend"
    enabled: bool = True


class CollectorConfig(BaseModel):
    """采集配置"""
    interval: int = 5
    timeout: int = 2
    retry_count: int = 2
    retry_delay: int = 1


class AggregatorConfig(BaseModel):
    """聚合配置"""
    period_hours: int = 1
    align_to_hour: bool = True


class RetentionConfig(BaseModel):
    """数据保留策略"""
    days: int = 30
    cleanup_hour: int = 3


class BackupConfig(BaseModel):
    """备份配置"""
    path: str = "ops/monitor/backup"
    retention_days: int = 7
    backup_hour: int = 4


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    file: Optional[str] = None
    max_size_mb: int = 50
    backup_count: int = 5


class AppConfig(BaseModel):
    """应用配置（完整配置）"""
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    frontend: FrontendConfig = Field(default_factory=FrontendConfig)
    collector: CollectorConfig = Field(default_factory=CollectorConfig)
    aggregator: AggregatorConfig = Field(default_factory=AggregatorConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """
    加载配置文件
    
    优先级：
    1. 参数指定的路径
    2. 环境变量 MONITOR_CONFIG_PATH
    3. 默认路径 ops/monitor/config.yaml
    """
    if config_path is None:
        config_path = os.environ.get(
            "MONITOR_CONFIG_PATH",
            "ops/monitor/config.yaml"
        )
    
    config_file = Path(config_path)
    
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
            if raw_config:
                # Normalize relative paths so the app doesn't depend on CWD.
                # Convention: config.yaml lives at <repo>/ops/monitor/config.yaml,
                # and paths inside config.yaml are repo-root-relative.
                try:
                    resolved_config = config_file.resolve()
                    # Expected layout: <repo>/ops/monitor/config.yaml
                    if resolved_config.parent.name == "monitor" and resolved_config.parent.parent.name == "ops":
                        repo_root = resolved_config.parents[2]
                    else:
                        # Fallback: treat paths as relative to the config file directory.
                        repo_root = resolved_config.parent
                except Exception:
                    repo_root = None

                def _resolve_repo_path(value: Optional[str]) -> Optional[str]:
                    if not value or not repo_root:
                        return value
                    path = Path(value)
                    if path.is_absolute():
                        return str(path)
                    return str((repo_root / path).resolve())

                raw_config.setdefault("database", {})
                raw_config["database"]["path"] = _resolve_repo_path(raw_config["database"].get("path"))

                raw_config.setdefault("frontend", {})
                raw_config["frontend"]["path"] = _resolve_repo_path(raw_config["frontend"].get("path"))

                raw_config.setdefault("backup", {})
                raw_config["backup"]["path"] = _resolve_repo_path(raw_config["backup"].get("path"))

                raw_config.setdefault("logging", {})
                raw_config["logging"]["file"] = _resolve_repo_path(raw_config["logging"].get("file"))

                return AppConfig(**raw_config)
    
    # 配置文件不存在时使用默认配置
    return AppConfig()


# 全局配置实例（延迟加载）
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置实例（单例模式）"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config():
    """重置配置（主要用于测试）"""
    global _config
    _config = None
