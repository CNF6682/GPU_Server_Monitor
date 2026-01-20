"""
配置管理模块

从 YAML 文件加载配置，支持环境变量覆盖
"""

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field


class ProxyConfig(BaseModel):
    """代理转发配置模型"""

    enabled: bool = Field(default=False, description="是否启用代理")
    server_listen_port: int = Field(..., description="Agent 本地监听端口")
    center_proxy_port: int = Field(..., description="中心节点代理端口")
    center_ssh_host: str = Field(..., description="中心节点 SSH 地址")
    center_ssh_port: int = Field(default=22, description="中心节点 SSH 端口")
    center_ssh_user: str = Field(..., description="SSH 用户名")
    identity_file: str = Field(..., description="SSH 私钥路径")
    strict_host_key_checking: bool = Field(default=True, description="是否严格检查 host key")
    auto_start: bool = Field(default=False, description="Agent 启动时自动启动代理")


class AgentConfig(BaseModel):
    """Agent 配置模型"""

    node_id: str = Field(..., description="节点唯一标识")
    listen: str = Field(default="0.0.0.0:9109", description="监听地址")
    token: str = Field(..., description="认证 Token")
    disks: List[str] = Field(default=["/"], description="监控的磁盘挂载点")
    services_allowlist: List[str] = Field(default=[], description="允许查询的 systemd 服务列表")
    gpu: str = Field(default="auto", description="GPU 采集模式: auto|off|nvidia")
    proxy: Optional[ProxyConfig] = Field(default=None, description="代理转发配置（可选）")

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
