#!/bin/bash
# harness WebUI 启动脚本

cd /home/ubuntu/ws/harness

echo "🚀 启动 harness WebUI..."
echo ""
echo "📡 API 端点:"
echo "   - 任务创建: http://localhost:7500/api/external/create_task"
echo "   - 任务状态: http://localhost:7500/api/external/task_status/<id>"
echo "   - 健康检查: http://localhost:7500/api/external/health"
echo ""
echo "🌐 WebUI: http://localhost:7500"
echo ""

# 检查依赖
if ! command -v uvicorn &> /dev/null; then
    echo "❌ uvicorn 未安装，正在安装..."
    pip install uvicorn fastapi
fi

# 启动
exec uvicorn webui.app.main:app --host 0.0.0.0 --port 7500 --reload
