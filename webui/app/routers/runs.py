from fastapi import APIRouter, Request, Depends, HTTPException, Cookie
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
import asyncio
import json

from app.database import get_db, init_db
from app.models import Run, RunStatus, Task, TaskStatus, Agent
from app.services.executor import TaskExecutor
from app.templates import templates
from app.auth import get_current_user
from app.i18n import get_lang, t as translate

router = APIRouter(prefix="/runs", tags=["runs"])


def _ctx(request: Request, lang: str | None, extra: dict = {}) -> dict:
    lang_code = get_lang(lang)
    ctx = {'lang': lang_code, 't': lambda key: translate(key, lang_code)}
    ctx.update(extra)
    return ctx


@router.get("", response_class=HTMLResponse)
async def runs_page(
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    runs = db.query(Run).order_by(Run.started_at.desc()).all()
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    return templates.TemplateResponse(request, "runs.html", _ctx(request, lang, {
        "runs": runs, "tasks": tasks
    }))


@router.get("/list", response_class=HTMLResponse)
async def runs_list(
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    runs = db.query(Run).order_by(Run.started_at.desc()).all()
    tasks = {t.id: t for t in db.query(Task).all()}
    agents = {a.id: a for a in db.query(Agent).all()}
    return templates.TemplateResponse(request, "partials/run_log.html", _ctx(request, lang, {
        "runs": runs, "tasks": tasks, "agents": agents
    }))


@router.get("/{run_id}/log", response_class=HTMLResponse)
async def run_log(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return templates.TemplateResponse(request, "partials/run_log_single.html", _ctx(request, lang, {
        "run": run
    }))


@router.post("/{run_id}/cancel", response_class=HTMLResponse)
async def cancel_run(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    TaskExecutor.cancel(run.task_id)

    run.status = RunStatus.failed
    run.finished_at = datetime.utcnow()
    run.log = (run.log or "") + "\n[キャンセル] 実行がキャンセルされました。\n"
    db.commit()

    task = db.query(Task).filter(Task.id == run.task_id).first()
    if task:
        task.status = TaskStatus.failed
        db.commit()

    return templates.TemplateResponse(request, "partials/run_log_single.html", _ctx(request, lang, {
        "run": run
    }))


@router.get("/{run_id}/log-stream")
async def run_log_stream(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user)
):
    """SSE endpoint for real-time log streaming"""
    init_db()
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_stream():
        last_length = 0
        while True:
            if await request.is_disconnected():
                break
            # Refresh run from DB
            db2 = next(get_db())
            try:
                current_run = db2.query(Run).filter(Run.id == run_id).first()
                if not current_run:
                    break
                current_log = current_run.log or ""
                if len(current_log) > last_length:
                    # Send full log content (client re-renders everything)
                    yield f"data: {json.dumps(current_log)}\n\n"
                    last_length = len(current_log)
                if current_run.status.value != "running":
                    # Send final log and close
                    yield f"data: {json.dumps(current_log)}\n\n"
                    break
            finally:
                db2.close()
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/{run_id}/log-raw", response_class=HTMLResponse)
async def run_log_raw(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    """Returns raw log content for polling / initial load"""
    init_db()
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.log or ""
