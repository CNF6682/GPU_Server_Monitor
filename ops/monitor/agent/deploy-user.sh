#!/bin/bash
set -euo pipefail

usage() {
  cat << 'EOF'
Usage: ./deploy-user.sh <node-id> <token> [listen]

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
  DISKS="/,/data" GPU_MODE=auto ./deploy-user.sh srv-01 mytoken 0.0.0.0:9109
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

NODE_ID="$1"
TOKEN="$2"
LISTEN="${3:-0.0.0.0:9109}"
DISKS="${DISKS:-/}"
SERVICES_ALLOWLIST="${SERVICES_ALLOWLIST:-}"
GPU_MODE="${GPU_MODE:-auto}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_SRC_DIR="$SCRIPT_DIR"
INSTALL_DIR="$HOME/monitor-agent"
CONFIG_DIR="$HOME/.config/monitor-agent"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
LOG_FILE="$HOME/monitor-agent.log"
PID_FILE="$HOME/monitor-agent.pid"

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

echo "==> Preparing directories"
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

echo "==> Starting agent in background"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Monitor Agent is already running with PID $(cat "$PID_FILE")"
else
  nohup env MONITOR_AGENT_CONFIG="$CONFIG_FILE" \
    "$INSTALL_DIR/venv/bin/python" -m monitor_agent >> "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "Monitor Agent started with PID $(cat "$PID_FILE")"
fi

echo "==> Done"
echo "Health check: curl http://127.0.0.1:${LISTEN##*:}/v1/health"
