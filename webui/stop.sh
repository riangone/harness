#!/bin/bash
SERVICE=harness-webui

if systemctl is-active --quiet "$SERVICE"; then
    echo "Stopping $SERVICE..."
    sudo systemctl stop "$SERVICE"
    echo "Stopped."
else
    # フォールバック: uvicornプロセスを直接終了
    PIDS=$(pgrep -f "uvicorn app.main:app")
    if [ -n "$PIDS" ]; then
        echo "Killing uvicorn processes: $PIDS"
        kill $PIDS
        echo "Stopped."
    else
        echo "$SERVICE is not running."
    fi
fi
