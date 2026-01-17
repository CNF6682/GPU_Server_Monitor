"""
工具函数模块
"""

import secrets


def generate_token(length: int = 32) -> str:
    """
    生成随机 Token

    Args:
        length: Token 长度

    Returns:
        URL 安全的随机字符串
    """
    return secrets.token_urlsafe(length)


if __name__ == "__main__":
    # 生成一个新的 Token
    print("Generated Token:")
    print(generate_token())
