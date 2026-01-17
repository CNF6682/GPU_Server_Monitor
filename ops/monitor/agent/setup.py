"""
Monitor Agent 安装配置
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="monitor-agent",
    version="1.0.0",
    description="Linux 服务器监控代理",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="AI-A",
    python_requires=">=3.8",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "pydantic>=2.0.0",
        "PyYAML>=6.0",
        "psutil>=5.9.0",
    ],
    entry_points={
        "console_scripts": [
            "monitor-agent=monitor_agent.__main__:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
