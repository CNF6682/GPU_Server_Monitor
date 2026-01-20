#!/bin/bash
set -euo pipefail

usage() {
  cat << 'EOF'
Usage: sudo ./deploy-one-click.sh <node-id> <token> [listen]

Required:
  node-id   Unique node identifier (e.g. srv-01)
  token     Shared auth token

Optional:
  listen    Listen address, default: 0.0.0.0:9109

Environment (optional):
  DISKS               Comma-separated mount points, default: /
  SERVICES_ALLOWLIST  Comma-separated systemd units, default: empty
  GPU_MODE            auto|nvidia|off, default: auto

Example:
  sudo DISKS="/,/data" GPU_MODE=auto ./deploy-one-click.sh srv-01 mytoken 0.0.0.0:9109
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

if [ "$#" -lt 2 ]; then
  usage
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run as root (use sudo)."
  exit 1
fi

NODE_ID="$1"
TOKEN="$2"
LISTEN="${3:-0.0.0.0:9109}"
DISKS="${DISKS:-/}"
SERVICES_ALLOWLIST="${SERVICES_ALLOWLIST:-}"
GPU_MODE="${GPU_MODE:-auto}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_SRC_DIR="$SCRIPT_DIR"
INSTALL_DIR="/opt/monitor-agent"
CONFIG_DIR="/etc/monitor-agent"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
SERVICE_FILE="/etc/systemd/system/monitor-agent.service"
LOG_FILE="/var/log/monitor-agent.log"
PID_FILE="/var/run/monitor-agent.pid"

format_yaml_list() {
  local csv="$1"
  local indent="$2"
  local IFS=','
  read -r -a items <<< "$csv"
  for item in "${items[@]}"; do
    local trimmed
    trimmed="$(echo "$item" | xargs)"
    if [ -n "$trimmed" ]; then
      echo "${indent}- \"${trimmed}\""
    fi
  done
}

detect_pkg_manager() {
  if command -v apt-get >/dev/null 2>&1; then
    echo "apt-get"
  elif command -v dnf >/dev/null 2>&1; then
    echo "dnf"
  elif command -v yum >/dev/null 2>&1; then
    echo "yum"
  else
    echo ""
  fi
}

install_packages() {
  local pm
  pm="$(detect_pkg_manager)"
  if [ -z "$pm" ]; then
    echo "No supported package manager found. Install python3, python3-venv, pip, curl, rsync manually."
    return 0
  fi

  if [ "$pm" = "apt-get" ]; then
    apt-get update -y
    apt-get install -y python3 python3-venv python3-pip curl rsync
  elif [ "$pm" = "dnf" ]; then
    dnf install -y python3 python3-pip curl rsync
  else
    yum install -y python3 python3-pip curl rsync
  fi
}

echo "==> Installing prerequisites"
install_packages

echo "==> Creating user and directories"
useradd --system --no-create-home --shell /usr/sbin/nologin monitor-agent 2>/dev/null || true
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR"

echo "==> Syncing agent code to $INSTALL_DIR"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "$AGENT_SRC_DIR"/ "$INSTALL_DIR"/
else
  rm -rf "$INSTALL_DIR"/*
  cp -a "$AGENT_SRC_DIR"/. "$INSTALL_DIR"/
fi

echo "==> Setting up Python virtual environment"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

echo "==> Writing config to $CONFIG_FILE"
if [ -f "$CONFIG_FILE" ]; then
  cp "$CONFIG_FILE" "${CONFIG_FILE}.bak.$(date +%Y%m%d%H%M%S)"
fi

{
  echo "node_id: \"${NODE_ID}\""
  echo "listen: \"${LISTEN}\""
  echo "token: \"${TOKEN}\""
  echo "disks:"
  format_yaml_list "$DISKS" "  "
  if [ -n "$SERVICES_ALLOWLIST" ]; then
    echo "services_allowlist:"
    format_yaml_list "$SERVICES_ALLOWLIST" "  "
  else
    echo "services_allowlist: []"
  fi
  echo "gpu: \"${GPU_MODE}\""
} > "$CONFIG_FILE"

chown -R monitor-agent:monitor-agent "$INSTALL_DIR" "$CONFIG_DIR"
chmod 640 "$CONFIG_FILE"

if command -v systemctl >/dev/null 2>&1; then
  echo "==> Installing systemd service"
  cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Monitor Agent
After=network.target

[Service]
Type=simple
User=monitor-agent
Group=monitor-agent
Restart=always
RestartSec=2
Environment=MONITOR_AGENT_CONFIG=$CONFIG_FILE
ExecStart=$INSTALL_DIR/venv/bin/python -m monitor_agent
WorkingDirectory=$INSTALL_DIR
MemoryLimit=100M
CPUQuota=5%
ExecStartPost=/bin/sleep 2
ExecStartPost=/usr/bin/curl -sf http://127.0.0.1:${LISTEN##*:}/v1/health || exit 0
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable --now monitor-agent
  systemctl status monitor-agent --no-pager
else
  echo "==> systemd not found; starting in background"
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Monitor Agent is already running with PID $(cat "$PID_FILE")"
  else
    nohup "$INSTALL_DIR/venv/bin/python" -m monitor_agent >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Monitor Agent started with PID $(cat "$PID_FILE")"
  fi
fi

echo "==> Done"
echo "Health check: curl http://127.0.0.1:${LISTEN##*:}/v1/health"
