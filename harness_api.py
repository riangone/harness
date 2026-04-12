"""
Harness API Server — 独立的 HTTP API 服务

两种启动方式：
1. 独立模式：python -m harness_api（或 uvicorn harness_api:app）
   - 作为独立的 FastAPI 服务运行
   - 不依赖 WebUI

2. 嵌入模式：被 WebUI 的 main.py include
   - 与 WebUI 共享进程和端口
   - 复用数据库连接

启动（独立模式）：
    uvicorn harness_api:app --host 0.0.0.0 --port 7500 --reload

环境变量：
    HARNESS_API_TOKEN      API 认证 Token
    HARNESS_DB_PATH        数据库路径（默认 webui/harness.db）
"""
import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = Path(__file__).parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 确保 webui/app 也在路径中
WEBUI_APP = PROJECT_ROOT / "webui" / "app"
if str(WEBUI_APP.parent) not in sys.path:
    sys.path.insert(0, str(WEBUI_APP.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("harness-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化"""
    logger.info("🚀 Harness API Server starting up")

    # 初始化数据库
    try:
        from app.database import init_db
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")

    yield

    logger.info("👋 Harness API Server shutting down")


app = FastAPI(
    title="Harness API",
    description="Multi-AI Agent Orchestrator — HTTP API for external systems",
    version="2.0.0",
    lifespan=lifespan
)

# CORS 中间件（允许 MailMindHub 跨域调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# カスタム 422 バリデーションエラーハンドラー
# FastAPI デフォルトの英語エラーを分かりやすい形式に変換
# ============================================
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic バリデーションエラーを分かりやすい JSON 形式で返す"""
    missing_fields = []
    invalid_fields = []

    for error in exc.errors():
        loc = error.get("loc", [])
        field = loc[-1] if loc else "unknown"
        err_type = error.get("type", "")
        msg = error.get("msg", "")

        if err_type in ("missing", "value_error.missing"):
            missing_fields.append(str(field))
        else:
            invalid_fields.append({"field": str(field), "message": msg})

    detail = {"error": "validation_error"}

    if missing_fields:
        detail["missing_fields"] = missing_fields
        detail["message"] = f"必須フィールドが不足しています: {', '.join(missing_fields)}"
        detail["hint"] = _get_validation_hint(request.url.path, missing_fields)

    if invalid_fields:
        detail["invalid_fields"] = invalid_fields
        if "message" not in detail:
            detail["message"] = "フィールドの値が不正です"

    logger.warning(f"Validation error on {request.method} {request.url.path}: {detail}")
    return JSONResponse(status_code=422, content=detail)


def _get_validation_hint(path: str, missing_fields: list) -> str:
    """エンドポイントパスと不足フィールドに基づいてヒントを返す"""
    if "/tasks/from-email" in path:
        return (
            'メールからのタスク作成には {"subject": "件名"} が必須です。'
            ' body と from_addr は省略可能です。'
        )
    if "/tasks" in path and ("title" in missing_fields or "prompt" in missing_fields):
        return (
            'タスク作成には title か prompt のいずれかが必要です。'
            ' 例: {"title": "タスク名"} または {"prompt": "指示内容"}'
        )
    return "API ドキュメントを確認してください: /docs"


# ============================================
# 注册路由
# ============================================

# 注册 external_api 路由（核心 API）
try:
    from app.routers import external_api
    app.include_router(external_api.router)
    logger.info("✅ External API routes registered")
except ImportError as e:
    logger.warning(f"⚠️ Could not import external_api routes: {e}")


# ============================================
# 根端点
# ============================================

@app.get("/")
async def root():
    """API 根 — 服务信息"""
    return {
        "service": "harness-api",
        "version": "2.0.0",
        "docs": "/docs",
        "mode": "standalone"
    }


# ============================================
# CLI 入口
# ============================================

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HARNESS_API_HOST", "0.0.0.0")
    port = int(os.environ.get("HARNESS_API_PORT", "7500"))
    reload = os.environ.get("HARNESS_API_RELOAD", "").lower() in ("1", "true", "yes")

    logger.info(f"Starting Harness API on {host}:{port} (reload={reload})")

    uvicorn.run(
        "harness_api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
