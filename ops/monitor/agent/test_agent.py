#!/usr/bin/env python3
"""
Monitor Agent 测试脚本

测试 Agent 的各个 API 端点
"""

import sys
import requests
import json


def test_agent(host="localhost", port=9109, token="test-token"):
    """
    测试 Agent API

    Args:
        host: Agent 主机地址
        port: Agent 端口
        token: 认证 Token
    """
    base_url = f"http://{host}:{port}"
    headers = {"Authorization": f"Bearer {token}"}

    print("=" * 60)
    print("Monitor Agent API 测试")
    print("=" * 60)
    print()

    # 测试健康检查端点（无需认证）
    print("1. 测试健康检查端点 (GET /v1/health)")
    print("-" * 60)
    try:
        response = requests.get(f"{base_url}/v1/health", timeout=5)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"健康状态: {data['status']}")
            print(f"检查结果:")
            for key, value in data['checks'].items():
                print(f"  - {key}: {value}")
            print("✅ 健康检查通过")
        else:
            print(f"❌ 健康检查失败: {response.text}")
    except Exception as e:
        print(f"❌ 请求失败: {e}")
    print()

    # 测试快照端点（需要认证）
    print("2. 测试快照端点 (GET /v1/snapshot)")
    print("-" * 60)
    try:
        response = requests.get(f"{base_url}/v1/snapshot", headers=headers, timeout=5)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"节点 ID: {data['node_id']}")
            print(f"采集时间: {data['ts']}")
            print(f"CPU 使用率: {data['cpu_pct']}%")
            print(f"磁盘信息: {len(data['disks'])} 个挂载点")
            if data['gpus']:
                print(f"GPU 信息: {len(data['gpus'])} 个 GPU")
            else:
                print("GPU 信息: 无")
            print(f"服务信息: {len(data['services'])} 个服务")
            print("✅ 快照获取成功")
            print()
            print("完整响应:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"❌ 快照获取失败: {response.text}")
    except Exception as e:
        print(f"❌ 请求失败: {e}")
    print()

    # 测试服务发现端点（需要认证）
    print("3. 测试服务发现端点 (GET /v1/services)")
    print("-" * 60)
    try:
        response = requests.get(f"{base_url}/v1/services", headers=headers, timeout=10)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"发现 {len(data)} 个服务")
            if data:
                print("前 5 个服务:")
                for svc in data[:5]:
                    print(f"  - {svc['name']}: {svc['active_state']} (enabled: {svc['enabled']})")
            print("✅ 服务发现成功")
        else:
            print(f"❌ 服务发现失败: {response.text}")
    except Exception as e:
        print(f"❌ 请求失败: {e}")
    print()

    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        host = sys.argv[1]
    else:
        host = "localhost"

    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    else:
        port = 9109

    if len(sys.argv) > 3:
        token = sys.argv[3]
    else:
        token = "test-token"

    test_agent(host, port, token)
