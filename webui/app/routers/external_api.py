"""
External API — harness HTTP API 層

供外部系统（MailMindHub 等）调用 harness 任务管道。
支持两种模式：
1. 轮询模式：创建任务 → 轮询 /tasks/{id} 获取状态
2. Webhook 模式：创建任务时传入 callback_url → 完成后主动 POST 结果

可独立部署（harness_api.py）或嵌入 WebUI（本文件）。
"""
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime
import logging
import threading
import traceback

from app.database import get_db, init_db
from app.models import Task, TaskStatus, Agent, Project, Run, RunStatus
from app.services.executor import execute_task
from core.gateway.mail import MailGateway

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["external-api"])

# ============================================
# API Token 认证
# ============================================
HARNESS_API_TOKEN = ""  # 从环境变量加载


def verify_api_token(x_api_key: str | None = Header(None)) -> bool:
    """验证 API Token"""
    global HARNESS_API_TOKEN
    if not HARNESS_API_TOKEN:
        HARNESS_API_TOKEN = __import__('os').environ.get("HARNESS_API_TOKEN", "")
    if not HARNESS_API_TOKEN:
        return True  # 开发模式：无 token 时允许所有请求
    return x_api_key == HARNESS_API_TOKEN


# ============================================
# 请求/响应模型
# ============================================
class TaskCreateRequest(BaseModel):
    """创建任务请求

    注意: title と prompt のどちらか一方があれば足ります。
    - prompt のみ指定 → title に先頭80文字が使われる
    - title のみ指定 → prompt に title がコピーされる
    """
    title: Optional[str] = Field(None, description="任务标题（省略時は prompt 先頭80文字）")
    prompt: Optional[str] = Field(None, description="任务提示（省略時は title を使用）")
    success_criteria: Optional[str] = Field(None, description="成功标准")
    pipeline_mode: bool = Field(True, description="是否使用 Pipeline 模式")
    agent_id: Optional[int] = Field(None, description="指定 Agent ID")
    project_id: Optional[int] = Field(None, description="项目 ID")
    callback_url: Optional[str] = Field(None, description="Webhook 回调地址（可选）")
    source: Optional[str] = Field(None, description="任务来源（email/cli/api）")
    metadata: Optional[Dict[str, Any]] = Field(None, description="额外元数据")


class TaskCreateResponse(BaseModel):
    """创建任务响应"""
    task_id: int
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: int
    status: str
    title: str
    prompt: Optional[str] = None
    result: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    runs: List[Dict[str, Any]] = []


class CallbackPayload(BaseModel):
    """Webhook 回调负载（harness → MailMindHub）"""
    task_id: int
    status: str  # completed / failed
    title: str
    result: Optional[str] = None
    from_addr: Optional[str] = None  # 原始发件人地址（供 MailMindHub 回复）
    runs: List[Dict[str, Any]] = []
    email_content: Optional[Dict[str, str]] = None  # {subject, body} 供 MailMindHub 回复邮件


class EmailTaskRequest(BaseModel):
    """从邮件直接创建任务（MailMindHub 转发邮件内容）

    body と from_addr は省略可能。
    - body 未指定 → 空文字列として扱い、subject からタスク内容を抽出
    - from_addr 未指定 → Webhook コールバックの from_addr フィールドが空になる
    """
    subject: str = Field(..., description="邮件主题（必须）")
    body: Optional[str] = Field("", description="邮件正文（省略可、デフォルト空文字）")
    from_addr: Optional[str] = Field(None, description="发件人地址（省略可）")
    callback_url: Optional[str] = Field(None, description="Webhook 回调地址")


class EmailTaskResponse(BaseModel):
    """邮件创建任务响应"""
    task_id: Optional[int] = None
    status: str
    message: str
    help_sent: bool = False


class HealthResponse(BaseModel):
    """健康检查"""
    status: str
    service: str
    version: str = "2.0.0"


class ListTasksResponse(BaseModel):
    """任务列表响应"""
    tasks: List[Dict[str, Any]]
    total: int


# ============================================
# Webhook 回调发送器
# ============================================
def _send_webhook_callback(task_id: int, db_session):
    """任务完成后发送 Webhook 回调"""
    from app.database import SessionLocal
    import requests as requests_lib

    db = db_session or SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return

        # 检查是否有回调 URL
        callback_url = None
        if task.task_meta:
            import json
            try:
                meta = json.loads(task.task_meta) if isinstance(task.task_meta, str) else task.task_meta
                callback_url = meta.get('callback_url')
            except (json.JSONDecodeError, TypeError):
                pass

        if not callback_url:
            return

        # 获取执行记录
        runs = db.query(Run).filter(Run.task_id == task_id).order_by(Run.started_at.asc()).all()
        run_data = []
        for run in runs:
            run_data.append({
                "phase": run.phase,
                "status": run.status.value if hasattr(run.status, 'value') else str(run.status),
                "result": run.log,
                "log_summary": (run.log or "")[:500],
                "agent": run.agent.name if run.agent else None,
                "attempt": run.attempt,
                "eval_verdict": run.eval_verdict,
            })

        # 格式化邮件内容（供 MailMindHub 回复用户）
        email_content = None
        try:
            mail_gateway = MailGateway()
            result_dict = {
                'success': task.status == TaskStatus.completed,
                'result': task.result,
                'step_results': {r.phase: {'success': r.status == RunStatus.completed, 'model_used': r.agent.name if r.agent else ''} for r in runs}
            }
            task_dict = {
                'id': task.id,
                'title': task.title,
                'input': task.prompt[:100],
                'from_addr': None
            }
            if task.task_meta:
                try:
                    import json
                    meta = json.loads(task.task_meta) if isinstance(task.task_meta, str) else task.task_meta
                    task_dict['from_addr'] = meta.get('from_addr')
                    task_dict['input'] = meta.get('input', task.prompt[:100])
                except (json.JSONDecodeError, TypeError):
                    pass

            email_content = mail_gateway.format_task_complete_response(task_dict, result_dict)
        except Exception as e:
            logger.warning(f"Failed to format email content: {e}")

        # 提取 from_addr
        from_addr = None
        if task.task_meta:
            try:
                import json
                meta = json.loads(task.task_meta) if isinstance(task.task_meta, str) else task.task_meta
                from_addr = meta.get('from_addr')
            except (json.JSONDecodeError, TypeError):
                pass

        payload = CallbackPayload(
            task_id=task.id,
            status=task.status.value if hasattr(task.status, 'value') else str(task.status),
            title=task.title,
            result=task.result,
            from_addr=from_addr,
            runs=run_data,
            email_content=email_content
        ).model_dump()

        # 发送 POST 请求
        resp = requests_lib.post(
            callback_url,
            json=payload,
            timeout=30,
            headers={"Content-Type": "application/json"}
        )
        resp.raise_for_status()
        logger.info(f"Webhook callback sent to {callback_url} for task {task_id}, status={resp.status_code}")

    except Exception as e:
        logger.error(f"Webhook callback failed for task {task_id}: {e}\n{traceback.format_exc()}")
    finally:
        if not db_session:
            db.close()


# ============================================
# Task Wrapper with Callback
# ============================================
def _execute_task_with_callback(task_id: int):
    """执行任务并在完成后发送 Webhook 回调"""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        execute_task(task_id)
    except Exception as e:
        logger.error(f"Task {task_id} execution failed: {e}")
    finally:
        db.close()

    # 任务完成后发送回调
    _send_webhook_callback(task_id, None)


# ============================================
# API 端点
# ============================================

@router.post("/tasks", response_model=TaskCreateResponse)
async def create_task(
    req: TaskCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_api_token)
):
    """
    创建并执行任务

    - **title**: 任务标题
    - **prompt**: 任务提示
    - **success_criteria**: 成功标准（可选）
    - **pipeline_mode**: 是否使用 Pipeline 模式（默认 True）
    - **agent_id**: 指定 Agent ID（可选）
    - **callback_url**: Webhook 回调地址（可选，完成后 POST 结果）

    返回 task_id，立即返回（异步执行）。
    如果传入 callback_url，harness 完成后会主动 POST 结果到该 URL。
    """
    try:
        init_db()

        # title / prompt の相互補完
        # どちらか一方でも指定されていれば受け付ける
        prompt = (req.prompt or "").strip()
        title = (req.title or "").strip()

        if not prompt and not title:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "validation_error",
                    "message": "title または prompt のいずれかは必須です",
                    "hint": "例: {\"title\": \"タスク名\", \"prompt\": \"詳細な指示\"}"
                }
            )

        if not prompt:
            prompt = title          # title だけの場合は prompt として使う
        if not title:
            title = prompt[:80]     # prompt だけの場合は先頭80文字をタイトルに

        # 构建元数据
        import json
        metadata = req.metadata or {}
        if req.callback_url:
            metadata['callback_url'] = req.callback_url
        if req.source:
            metadata['source'] = req.source

        task = Task(
            title=title,
            prompt=prompt,
            success_criteria=req.success_criteria or "",
            agent_id=req.agent_id,
            project_id=req.project_id,
            pipeline_mode=req.pipeline_mode,
            status=TaskStatus.pending,
            source=req.source or "api",
            task_meta=json.dumps(metadata) if metadata else None
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        logger.info(f"Task created via API: id={task.id}, title={task.title}, callback={'yes' if req.callback_url else 'no'}")

        # 后台执行任务
        background_tasks.add_task(_execute_task_with_callback, task.id)

        return TaskCreateResponse(
            task_id=task.id,
            status="pending",
            message="任务已创建，正在后台执行"
        )

    except Exception as e:
        logger.error(f"Failed to create task: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/from-email", response_model=EmailTaskResponse)
async def create_task_from_email(
    req: EmailTaskRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_api_token)
):
    """
    从邮件内容创建任务（MailMindHub 转发调用）

    MailMindHub 收到邮件后，将内容转发到此端点。
    harness 自动解析邮件内容、匹配路由规则、创建对应任务。
    """
    try:
        init_db()

        # body / from_addr は Optional なので None を空文字列に正規化
        body = req.body or ""
        from_addr = req.from_addr or ""

        # 使用 MailGateway 解析邮件内容
        mail_gateway = MailGateway()
        task_data = mail_gateway.parse_email_to_task(
            subject=req.subject,
            body=body,
            from_addr=from_addr,
            callback_url=req.callback_url
        )

        if not task_data:
            # 无法解析，返回帮助
            help_content = mail_gateway.generate_help_reply()
            return EmailTaskResponse(
                status="unknown_command",
                message="无法识别的命令，已生成帮助信息",
                help_sent=True
            )

        # タスクコンテンツが空の場合のガード
        task_input = (task_data.get('input') or "").strip()
        if not task_input:
            task_input = req.subject.strip()
        if not task_input:
            return EmailTaskResponse(
                status="error",
                message="タスク内容を抽出できませんでした。件名か本文に具体的な指示を記入してください。",
                help_sent=False
            )

        # 构建元数据
        import json
        metadata = task_data.get('metadata', {})
        if req.callback_url:
            metadata['callback_url'] = req.callback_url
        metadata['from_addr'] = from_addr
        metadata['subject'] = req.subject
        metadata['task_type'] = task_data.get('task_type', 'general')
        metadata['input'] = task_input

        task = Task(
            title=f"[email] {task_input[:80]}",
            prompt=task_input,
            success_criteria="",
            pipeline_mode=True,
            status=TaskStatus.pending,
            source="email",
            task_meta=json.dumps(metadata)
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        logger.info(f"Email task created: id={task.id}, pipeline={task_data['pipeline']}")

        # 后台执行
        background_tasks.add_task(_execute_task_with_callback, task.id)

        return EmailTaskResponse(
            task_id=task.id,
            status="pending",
            message=f"任务已创建，Pipeline: {task_data['pipeline']}"
        )

    except Exception as e:
        logger.error(f"Failed to create email task: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: int,
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_api_token)
):
    """
    查询任务状态和结果

    支持轮询模式：创建任务后定期调用此端点获取最新状态。
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    runs = db.query(Run).filter(Run.task_id == task_id).order_by(Run.started_at.asc()).all()
    run_data = []
    for run in runs:
        run_data.append({
            "phase": run.phase,
            "status": run.status.value if hasattr(run.status, 'value') else str(run.status),
            "result": run.log,
            "agent": run.agent.name if run.agent else None,
            "attempt": run.attempt,
            "eval_verdict": run.eval_verdict,
            "started_at": str(run.started_at) if run.started_at else None,
            "finished_at": str(run.finished_at) if run.finished_at else None,
        })

    return TaskStatusResponse(
        task_id=task.id,
        status=task.status.value if hasattr(task.status, 'value') else str(task.status),
        title=task.title,
        prompt=task.prompt,
        result=task.result,
        source=task.source,
        created_at=str(task.created_at) if task.created_at else None,
        completed_at=str(task.updated_at) if task.updated_at else None,
        runs=run_data
    )


@router.get("/tasks", response_model=ListTasksResponse)
async def list_tasks(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    source: Optional[str] = None,
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_api_token)
):
    """
    查询任务列表

    - **limit**: 返回数量（默认 20）
    - **offset**: 偏移量
    - **status**: 按状态过滤（pending/running/completed/failed）
    - **source**: 按来源过滤（email/api/cli）
    """
    query = db.query(Task)
    if status:
        query = query.filter(Task.status == status)
    if source:
        query = query.filter(Task.source == source)

    total = query.count()
    tasks = query.order_by(Task.created_at.desc()).offset(offset).limit(limit).all()

    task_list = []
    for t in tasks:
        task_list.append({
            "task_id": t.id,
            "title": t.title,
            "status": t.status.value if hasattr(t.status, 'value') else str(t.status),
            "source": t.source,
            "created_at": str(t.created_at) if t.created_at else None,
        })

    return ListTasksResponse(tasks=task_list, total=total)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: int,
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_api_token)
):
    """取消正在执行的任务"""
    from app.services.executor import TaskExecutor

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.status != TaskStatus.running:
        raise HTTPException(status_code=400, detail=f"Task {task_id} is not running (status: {task.status})")

    cancelled = TaskExecutor.cancel(task_id)
    if cancelled:
        task.status = TaskStatus.failed
        db.commit()
        return {"task_id": task_id, "status": "cancelled", "message": "任务已取消"}
    else:
        raise HTTPException(status_code=500, detail="取消失败，任务可能已完成")


@router.get("/agents")
async def list_agents(
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_api_token)
):
    """
    查询可用 Agent 列表

    用于 MailMindHub 展示可用的 Pipeline 类型。
    """
    agents = db.query(Agent).filter(Agent.is_active == True).order_by(Agent.priority.asc()).all()
    result = []
    for a in agents:
        result.append({
            "id": a.id,
            "name": a.name,
            "role": a.role,
            "cli_command": a.cli_command,
            "priority": a.priority,
        })
    return {"agents": result}


@router.post("/callback/test")
async def test_callback(
    callback_url: str = Header(..., alias="X-Callback-URL"),
    authorized: bool = Depends(verify_api_token)
):
    """
    测试 Webhook 回调

    向指定的 X-Callback-URL 发送测试 payload。
    用于 MailMindHub 验证回调端点是否正常工作。
    """
    import requests as requests_lib

    test_payload = {
        "task_id": 0,
        "status": "completed",
        "title": "Test Callback",
        "result": "This is a test callback from harness",
        "runs": [],
        "email_content": {
            "subject": "[harness] Test Callback",
            "body": "If you receive this, your webhook endpoint is working correctly."
        }
    }

    try:
        resp = requests_lib.post(callback_url, json=test_payload, timeout=10)
        return {"status": "ok", "response_code": resp.status_code, "url": callback_url}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Callback test failed: {str(e)}")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查端点"""
    return HealthResponse(status="ok", service="harness")
