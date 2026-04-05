#!/bin/bash
SERVICE=harness-webui

if systemctl list-unit-files --quiet "$SERVICE.service" 2>/dev/null | grep -q "$SERVICE"; then
    echo "Restarting $SERVICE..."
    sudo systemctl restart "$SERVICE"
    echo "Restarted. Status:"
    systemctl status "$SERVICE" --no-pager -l
else
    # フォールバック: 停止してから起動
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    echo "Stopping..."
    PIDS=$(pgrep -f "uvicorn app.main:app")
    [ -n "$PIDS" ] && kill $PIDS && sleep 1
    echo "Starting..."
    bash "$SCRIPT_DIR/start.sh" &
    echo "Started (PID: $!)"
fi
