#!/usr/bin/env bash
# Simple deployment helper for Linux/macOS
# Usage: ./deploy_agent.sh --api-key KEY --server-url https://your-bot.example.com

set -euo pipefail

VENV_PATH="${VENV_PATH:-$HOME/zoom_agent_venv}"
AGENT_DIR="${AGENT_DIR:-$(pwd)/agent}"
API_KEY=""
SERVER_URL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-key)
      API_KEY="$2"; shift 2;;
    --server-url)
      SERVER_URL="$2"; shift 2;;
    --venv)
      VENV_PATH="$2"; shift 2;;
    --agent-dir)
      AGENT_DIR="$2"; shift 2;;
    *) echo "Unknown arg $1"; exit 1;;
  esac
done

if [ -z "$API_KEY" ]; then
  echo "--api-key is required" >&2
  exit 1
fi

mkdir -p "$AGENT_DIR"
if [ ! -d "$VENV_PATH" ]; then
  python3 -m venv "$VENV_PATH"
fi
source "$VENV_PATH/bin/activate"
pip install --upgrade pip
pip install aiohttp pyautogui

RUN_CMD="python $AGENT_DIR/agent_server.py --api-key '$API_KEY'"
if [ -n "$SERVER_URL" ]; then
  RUN_CMD="$RUN_CMD --server-url '$SERVER_URL'"
fi

echo "Run command:"
echo "$RUN_CMD"

# Create systemd unit template (requires root to install)
UNIT_PATH="/etc/systemd/system/zoom-agent.service"
cat <<EOF
[Unit]
Description=Zoom Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$AGENT_DIR
ExecStart=$VENV_PATH/bin/python $AGENT_DIR/agent_server.py --api-key '$API_KEY' ${SERVER_URL:+--server-url '$SERVER_URL'}
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

echo
echo "If you want to install systemd unit, save the block above to $UNIT_PATH as root and run:\n  sudo systemctl daemon-reload && sudo systemctl enable --now zoom-agent"
