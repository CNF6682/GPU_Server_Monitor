"""
Monitor Agent 主程序入口

使用方式:
    python -m monitor_agent
    或
    uvicorn monitor_agent.app:app --host 0.0.0.0 --port 9109
"""

import sys
import uvicorn

from monitor_agent.config import get_config


def main():
    """主程序入口"""
    try:
        config = get_config()

        print(f"Starting Monitor Agent...")
        print(f"Node ID: {config.node_id}")
        print(f"Listening on: {config.listen}")

        # 启动 uvicorn 服务器
        uvicorn.run(
            "monitor_agent.app:app",
            host=config.host,
            port=config.port,
            log_level="info",
            access_log=True
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Please create config file at /etc/monitor-agent/config.yaml", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
