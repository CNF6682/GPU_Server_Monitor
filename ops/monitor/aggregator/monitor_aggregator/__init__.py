"""
Monitor Aggregator - Windows 中心节点服务

负责：
- 每 5s 拉取所有 Agent 数据
- 维护内存缓存供前端 5s 刷新
- 每小时聚合数据并入库
- 检测状态变化并生成事件
- 提供 REST API 给前端
"""

__version__ = "1.0.0"
__author__ = "AI-B"
