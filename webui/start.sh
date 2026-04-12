#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate 2>/dev/null || true

# 将 webui 目录和项目根目录都加入 PYTHONPATH
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/webui:$PYTHONPATH"

# 使用 --app-dir 指定 app 模块的位置
uvicorn app.main:app --host 0.0.0.0 --port 10000 --reload --app-dir "$PROJECT_ROOT/webui"
