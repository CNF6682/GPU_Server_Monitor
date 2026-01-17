#!/bin/bash
# ============================================================================
# Monitor Agent 自动化部署脚本
# 
# 用法: ./deploy-agent.sh <server-ip> <node-id> <token> [center-ip]
# 
# 参数:
#   server-ip   - 目标 Linux 服务器 IP 地址
#   node-id     - 节点 ID（唯一标识，如 srv-01）
#   token       - Agent Token（与中心节点共享）
#   center-ip   - 中心节点 IP（可选，用于配置防火墙）
# 
# 示例:
#   ./deploy-agent.sh 10.0.0.101 srv-01 abc123xyz 10.0.0.10
# ============================================================================

set -e  # 遇到错误立即退出

# ----------------------------------------------------------------------------
# 参数检查
# ----------------------------------------------------------------------------
if [ $# -lt 3 ]; then
    echo "❌ 用法: $0 <server-ip> <node-id> <token> [center-ip]"
    echo ""
    echo "参数说明:"
    echo "  server-ip   目标 Linux 服务器 IP"
    echo "  node-id     节点 ID（唯一标识）"
    echo "  token       Agent Token"
    echo "  center-ip   中心节点 IP（可选，配置防火墙用）"
    echo ""
    echo "示例:"
    echo "  $0 10.0.0.101 srv-01 my-secret-token 10.0.0.10"
    exit 1
fi

SERVER_IP=$1
NODE_ID=$2
TOKEN=$3
CENTER_IP=${4:-""}
AGENT_PORT=9109
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_SRC_DIR="$(dirname "$SCRIPT_DIR")/agent"

echo "============================================"
echo "  Monitor Agent 部署脚本"
echo "============================================"
echo ""
echo "目标服务器: $SERVER_IP"
echo "节点 ID:    $NODE_ID"
echo "Agent 端口: $AGENT_PORT"
echo ""

# ----------------------------------------------------------------------------
# Step 1: 检查本地 agent 代码是否存在
# ----------------------------------------------------------------------------
echo "[1/7] 检查本地 Agent 代码..."
if [ ! -d "$AGENT_SRC_DIR" ]; then
    echo "❌ 错误: Agent 代码目录不存在: $AGENT_SRC_DIR"
    exit 1
fi
echo "✅ Agent 代码目录: $AGENT_SRC_DIR"

# ----------------------------------------------------------------------------
# Step 2: 测试 SSH 连接
# ----------------------------------------------------------------------------
echo ""
echo "[2/7] 测试 SSH 连接..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes root@$SERVER_IP "echo 'SSH OK'" 2>/dev/null; then
    echo "❌ 错误: 无法通过 SSH 连接到 $SERVER_IP"
    echo ""
    echo "请确保："
    echo "  1. 目标服务器已启动"
    echo "  2. SSH 服务正在运行"
    echo "  3. 已配置 SSH 密钥免密登录"
    echo ""
    echo "配置 SSH 密钥:"
    echo "  ssh-copy-id root@$SERVER_IP"
    exit 1
fi
echo "✅ SSH 连接成功"

# ----------------------------------------------------------------------------
# Step 3: 创建用户和目录
# ----------------------------------------------------------------------------
echo ""
echo "[3/7] 创建系统用户和目录..."
ssh root@$SERVER_IP << 'REMOTE_SCRIPT'
# 创建系统用户（无登录 shell）
useradd --system --no-create-home --shell /usr/sbin/nologin monitor-agent 2>/dev/null || true

# 创建目录
mkdir -p /opt/monitor-agent
mkdir -p /etc/monitor-agent
chown -R root:root /opt/monitor-agent /etc/monitor-agent
chmod 755 /opt/monitor-agent /etc/monitor-agent
REMOTE_SCRIPT
echo "✅ 用户和目录创建完成"

# ----------------------------------------------------------------------------
# Step 4: 上传代码
# ----------------------------------------------------------------------------
echo ""
echo "[4/7] 上传 Agent 代码..."
scp -r "$AGENT_SRC_DIR"/* root@$SERVER_IP:/opt/monitor-agent/
echo "✅ 代码上传完成"

# ----------------------------------------------------------------------------
# Step 5: 安装 Python 环境和依赖
# ----------------------------------------------------------------------------
echo ""
echo "[5/7] 安装 Python 环境和依赖..."
ssh root@$SERVER_IP << 'REMOTE_SCRIPT'
# 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "正在安装 Python3..."
    if command -v apt-get &> /dev/null; then
        apt-get update && apt-get install -y python3 python3-venv python3-pip
    elif command -v yum &> /dev/null; then
        yum install -y python3 python3-pip
    elif command -v dnf &> /dev/null; then
        dnf install -y python3 python3-pip
    else
        echo "❌ 无法识别包管理器，请手动安装 Python3"
        exit 1
    fi
fi

# 创建虚拟环境
python3 -m venv /opt/monitor-agent/venv

# 安装依赖
/opt/monitor-agent/venv/bin/pip install --upgrade pip
/opt/monitor-agent/venv/bin/pip install -r /opt/monitor-agent/requirements.txt
REMOTE_SCRIPT
echo "✅ Python 环境配置完成"

# ----------------------------------------------------------------------------
# Step 6: 生成配置文件
# ----------------------------------------------------------------------------
echo ""
echo "[6/7] 生成配置文件..."
ssh root@$SERVER_IP "cat > /etc/monitor-agent/config.yaml << EOF
# Monitor Agent 配置文件
# 生成时间: $(date -u +"%Y-%m-%dT%H:%M:%SZ")

# 节点唯一标识
node_id: \"$NODE_ID\"

# 监听地址和端口
listen: \"0.0.0.0:$AGENT_PORT\"

# 与中心节点共享的 Token
token: \"$TOKEN\"

# 需要监控的磁盘挂载点
disks:
  - \"/\"

# 允许查询的 systemd 服务列表（留空表示不监控服务）
services_allowlist: []

# GPU 采集模式: auto|off|nvidia
gpu: \"nvidia\"
EOF"
echo "✅ 配置文件生成完成"

# ----------------------------------------------------------------------------
# Step 7: 配置 systemd 服务
# ----------------------------------------------------------------------------
echo ""
echo "[7/7] 配置并启动 systemd 服务..."
ssh root@$SERVER_IP "cat > /etc/systemd/system/monitor-agent.service << EOF
[Unit]
Description=Monitor Agent - Server Monitoring Agent
Documentation=https://github.com/your-org/monitor-agent
After=network.target

[Service]
Type=simple
User=root
Group=root
Restart=always
RestartSec=2

# 环境变量
Environment=MONITOR_AGENT_CONFIG=/etc/monitor-agent/config.yaml

# 启动命令
ExecStart=/opt/monitor-agent/venv/bin/python -m monitor_agent

# 工作目录
WorkingDirectory=/opt/monitor-agent

# 资源限制
MemoryLimit=100M
CPUQuota=5%

# 健康检查（启动后验证）
ExecStartPost=/bin/sleep 2
ExecStartPost=/usr/bin/curl -sf http://127.0.0.1:$AGENT_PORT/v1/health || exit 0

# 优雅停止
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=10

# 标准输出到 journal
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 重载并启动服务
systemctl daemon-reload
systemctl enable monitor-agent
systemctl restart monitor-agent
"
echo "✅ systemd 服务配置完成"

# ----------------------------------------------------------------------------
# 防火墙配置提示
# ----------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  部署完成！"
echo "============================================"
echo ""
echo "✅ Agent 已部署到: $SERVER_IP"
echo "✅ 节点 ID: $NODE_ID"
echo "✅ 监听端口: $AGENT_PORT"
echo ""

# 检查服务状态
echo "正在检查服务状态..."
if ssh root@$SERVER_IP "systemctl is-active monitor-agent" 2>/dev/null | grep -q "active"; then
    echo "✅ 服务状态: 运行中"
else
    echo "⚠️  服务状态: 可能未正常启动，请检查日志"
    echo "   查看日志: ssh root@$SERVER_IP 'journalctl -u monitor-agent -n 50'"
fi

echo ""
echo "📌 防火墙配置提示（请在目标服务器上执行）："
echo ""
if [ -n "$CENTER_IP" ]; then
    echo "   # UFW (Ubuntu/Debian)"
    echo "   sudo ufw allow from $CENTER_IP to any port $AGENT_PORT proto tcp"
    echo ""
    echo "   # firewalld (RHEL/CentOS)"
    echo "   sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=$CENTER_IP port port=$AGENT_PORT protocol=tcp accept'"
    echo "   sudo firewall-cmd --reload"
else
    echo "   提示: 未指定中心节点 IP，请手动配置防火墙规则"
    echo "   示例: sudo ufw allow from <CENTER_IP> to any port $AGENT_PORT proto tcp"
fi

echo ""
echo "📌 测试连接（从中心节点执行）："
echo "   curl -H \"Authorization: Bearer $TOKEN\" http://$SERVER_IP:$AGENT_PORT/v1/snapshot"
echo ""
echo "📌 查看日志："
echo "   ssh root@$SERVER_IP 'journalctl -u monitor-agent -f'"
echo ""
