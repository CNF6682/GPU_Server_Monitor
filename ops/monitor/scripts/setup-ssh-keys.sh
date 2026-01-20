#!/bin/bash
# ============================================================================
# SSH 密钥设置脚本（Linux Agent -> Windows Center）
# 
# 用法: ./setup-ssh-keys.sh [OPTIONS]
# 
# 选项:
#   -u, --user USER          SSH用户名（默认: dhga）
#   -h, --host HOST          中心节点主机名/IP（必需）
#   -p, --port PORT          SSH端口（默认: 22）
#   -f, --force              强制重新生成密钥
#   --key-type TYPE          密钥类型: ed25519|rsa（默认: ed25519）
#   --no-test                跳过连接测试
#   --help                   显示帮助
# 
# 说明:
#   此脚本用于在 Linux Agent 服务器上设置 SSH 密钥，
#   以便代理转发功能能够通过 SSH 隧道连接到 Windows 中心节点。
# 
# 前置条件:
#   - Windows 中心节点已安装并配置 OpenSSH Server
#   - 中心节点防火墙允许 TCP 22 入站
#   - 当前用户具有 sudo 权限（或以 root 运行）
# ============================================================================

set -e

# ----------------------------------------------------------------------------
# 默认配置
# ----------------------------------------------------------------------------
SSH_USER="${MONITOR_SSH_USER:-dhga}"
SSH_HOST=""
SSH_PORT="${MONITOR_SSH_PORT:-22}"
KEY_TYPE="ed25519"
KEY_COMMENT="monitor-agent-proxy"
FORCE_REGEN=false
SKIP_TEST=false

# 密钥路径
KEY_DIR="${HOME}/.ssh"
KEY_NAME="id_ed25519_monitor"

# ----------------------------------------------------------------------------
# 颜色输出
# ----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1" >&2
}

# ----------------------------------------------------------------------------
# 帮助信息
# ----------------------------------------------------------------------------
show_help() {
    cat << EOF
SSH 密钥设置脚本（用于监控系统代理转发）

用法: $0 [OPTIONS]

选项:
  -u, --user USER          SSH用户名（默认: dhga）
  -h, --host HOST          中心节点主机名/IP（必需）
  -p, --port PORT          SSH端口（默认: 22）
  -f, --force              强制重新生成密钥
  --key-type TYPE          密钥类型: ed25519|rsa（默认: ed25519）
  --no-test                跳过连接测试
  --help                   显示帮助

示例:
  $0 -h 192.168.1.100 -u admin
  $0 --host center.local --port 2222 --force

环境变量:
  MONITOR_SSH_USER         默认SSH用户名
  MONITOR_SSH_PORT         默认SSH端口

EOF
}

# ----------------------------------------------------------------------------
# 参数解析
# ----------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--user)
            SSH_USER="$2"
            shift 2
            ;;
        -h|--host)
            SSH_HOST="$2"
            shift 2
            ;;
        -p|--port)
            SSH_PORT="$2"
            shift 2
            ;;
        -f|--force)
            FORCE_REGEN=true
            shift
            ;;
        --key-type)
            KEY_TYPE="$2"
            shift 2
            ;;
        --no-test)
            SKIP_TEST=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            echo "使用 --help 查看帮助"
            exit 1
            ;;
    esac
done

# 验证必需参数
if [[ -z "$SSH_HOST" ]]; then
    log_error "缺少必需参数: --host"
    echo "使用 --help 查看帮助"
    exit 1
fi

# 设置密钥名称（根据类型）
if [[ "$KEY_TYPE" == "rsa" ]]; then
    KEY_NAME="id_rsa_monitor"
fi

KEY_FILE="${KEY_DIR}/${KEY_NAME}"

# ----------------------------------------------------------------------------
# 主程序
# ----------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  SSH 密钥设置 - 监控系统代理转发"
echo "============================================"
echo ""

# Step 1: 检查 SSH 客户端
log_info "检查 SSH 客户端..."
if ! command -v ssh &> /dev/null; then
    log_error "未找到 ssh 命令，请安装 openssh-client"
    echo "  Ubuntu/Debian: sudo apt install openssh-client"
    echo "  RHEL/CentOS:   sudo yum install openssh-clients"
    exit 1
fi
SSH_VERSION=$(ssh -V 2>&1 | head -1)
log_success "SSH 客户端: $SSH_VERSION"

# Step 2: 创建 .ssh 目录
log_info "检查 .ssh 目录..."
if [[ ! -d "$KEY_DIR" ]]; then
    mkdir -p "$KEY_DIR"
    chmod 700 "$KEY_DIR"
    log_success "创建目录: $KEY_DIR"
else
    log_success "目录已存在: $KEY_DIR"
fi

# Step 3: 生成密钥对
log_info "检查 SSH 密钥..."
if [[ -f "$KEY_FILE" ]] && [[ "$FORCE_REGEN" != "true" ]]; then
    log_success "密钥已存在: $KEY_FILE"
    log_info "使用 --force 参数可强制重新生成"
else
    if [[ -f "$KEY_FILE" ]]; then
        log_warning "备份现有密钥..."
        mv "$KEY_FILE" "${KEY_FILE}.bak.$(date +%Y%m%d%H%M%S)"
        mv "${KEY_FILE}.pub" "${KEY_FILE}.pub.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
    fi
    
    log_info "生成新的 $KEY_TYPE 密钥..."
    if [[ "$KEY_TYPE" == "ed25519" ]]; then
        ssh-keygen -t ed25519 -f "$KEY_FILE" -C "$KEY_COMMENT" -N ""
    else
        ssh-keygen -t rsa -b 4096 -f "$KEY_FILE" -C "$KEY_COMMENT" -N ""
    fi
    
    chmod 600 "$KEY_FILE"
    chmod 644 "${KEY_FILE}.pub"
    log_success "密钥生成完成: $KEY_FILE"
fi

# Step 4: 显示公钥
echo ""
echo "============================================"
echo "  公钥内容（需复制到中心节点）"
echo "============================================"
echo ""
cat "${KEY_FILE}.pub"
echo ""

# Step 5: 创建 SSH 配置
log_info "配置 SSH..."
SSH_CONFIG="${KEY_DIR}/config"

# 检查是否已有相关配置
if grep -q "Host monitor-center" "$SSH_CONFIG" 2>/dev/null; then
    log_warning "SSH 配置已存在 (Host monitor-center)"
    log_info "如需更新，请手动编辑 $SSH_CONFIG"
else
    # 添加配置
    cat >> "$SSH_CONFIG" << EOF

# 监控系统代理转发连接
Host monitor-center
    HostName $SSH_HOST
    User $SSH_USER
    Port $SSH_PORT
    IdentityFile $KEY_FILE
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new
EOF
    chmod 600 "$SSH_CONFIG"
    log_success "已添加 SSH 配置 (Host monitor-center)"
fi

# Step 6: 提示公钥安装
echo ""
echo "============================================"
echo "  下一步：在 Windows 中心节点安装公钥"
echo "============================================"
echo ""
echo "请执行以下操作："
echo ""
echo "1. 复制上面的公钥内容"
echo ""
echo "2. 在 Windows 中心节点执行（普通用户）："
echo "   \$pubkey = \"$(cat ${KEY_FILE}.pub)\""
echo "   Add-Content -Path \"\$env:USERPROFILE\\.ssh\\authorized_keys\" -Value \$pubkey"
echo ""
echo "3. 或者（管理员用户）："
echo "   \$pubkey = \"$(cat ${KEY_FILE}.pub)\""
echo "   Add-Content -Path \"C:\\ProgramData\\ssh\\administrators_authorized_keys\" -Value \$pubkey"
echo ""

# Step 7: 测试连接（可选）
if [[ "$SKIP_TEST" != "true" ]]; then
    echo ""
    log_info "尝试测试 SSH 连接..."
    echo "按 Ctrl+C 跳过，或等待 10 秒..."
    echo ""
    
    # 先尝试连接（可能需要确认 host key）
    if timeout 15 ssh -o BatchMode=yes -o ConnectTimeout=10 monitor-center "echo '连接成功！'" 2>/dev/null; then
        log_success "SSH 连接测试成功！"
    else
        log_warning "SSH 连接测试失败"
        echo ""
        echo "常见原因："
        echo "  1. 公钥尚未添加到中心节点"
        echo "  2. 中心节点 OpenSSH Server 未启动"
        echo "  3. 防火墙阻止 TCP $SSH_PORT"
        echo ""
        echo "完成公钥配置后，手动测试："
        echo "  ssh monitor-center"
        echo ""
    fi
fi

# 完成
echo ""
echo "============================================"
echo "  设置完成"
echo "============================================"
echo ""
echo "密钥文件:"
echo "  私钥: $KEY_FILE"
echo "  公钥: ${KEY_FILE}.pub"
echo ""
echo "Agent 代理配置参考:"
echo "  identity_file: $KEY_FILE"
echo "  center_ssh_host: $SSH_HOST"
echo "  center_ssh_port: $SSH_PORT"
echo "  center_ssh_user: $SSH_USER"
echo ""
