"""
配置管理模块

从 YAML 文件加载配置，支持环境变量覆盖
"""

import os
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Agent 配置模型"""

    node_id: str = Field(..., description="节点唯一标识")
    listen: str = Field(default="0.0.0.0:9109", description="监听地址")
    token: str = Field(..., description="认证 Token")
    disks: List[str] = Field(default=["/"], description="监控的磁盘挂载点")
    services_allowlist: List[str] = Field(default=[], description="允许查询的 systemd 服务列表")
    gpu: str = Field(default="auto", description="GPU 采集模式: auto|off|nvidia")

    @property
    def host(self) -> str:
        """获取监听主机"""
        return self.listen.split(":")[0]

    @property
    def port(self) -> int:
        """获取监听端口"""
        return int(self.listen.split(":")[1])


def load_config(config_path: str = None) -> AgentConfig:
    """
    加载配置文件

    Args:
        config_path: 配置文件路径，默认为 /etc/monitor-agent/config.yaml

    Returns:
        AgentConfig 实例
    """
    if config_path is None:
        config_path = os.getenv(
            "MONITOR_AGENT_CONFIG",
            "/etc/monitor-agent/config.yaml"
        )

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_file, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    return AgentConfig(**config_data)


# 全局配置实例（延迟加载）
_config: AgentConfig = None


def get_config() -> AgentConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = load_config()
    return _config
