from fastapi import APIRouter, Request, Form, Depends, HTTPException, Cookie
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional
import threading

from app.database import get_db, init_db
from app.models import Task, TaskStatus, Agent, Project
from app.services.executor import execute_task
from app.templates import templates
from app.auth import get_current_user
from app.i18n import get_lang, t as translate

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _ctx(request: Request, lang: str | None, extra: dict = {}) -> dict:
    lang_code = get_lang(lang)
    ctx = {'lang': lang_code, 't': lambda key: translate(key, lang_code)}
    ctx.update(extra)
    return ctx


@router.get("", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    agents = db.query(Agent).filter(Agent.is_active == True).all()
    projects = db.query(Project).all()
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    return templates.TemplateResponse(request, "tasks.html", _ctx(request, lang, {
        "tasks": tasks, "agents": agents, "projects": projects
    }))


@router.get("/list", response_class=HTMLResponse)
async def tasks_list(
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    agents = db.query(Agent).filter(Agent.is_active == True).all()
    projects = db.query(Project).all()
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    return templates.TemplateResponse(request, "partials/task_row.html", _ctx(request, lang, {
        "tasks": tasks, "agents": agents, "projects": projects
    }))


@router.post("", response_class=HTMLResponse)
async def create_task(
    request: Request,
    title: str = Form(...),
    prompt: str = Form(...),
    project_id: Optional[str] = Form(None),
    agent_id: Optional[str] = Form(None),
    pipeline_mode: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    task = Task(
        title=title,
        prompt=prompt,
        project_id=int(project_id) if project_id and project_id.strip() else None,
        agent_id=int(agent_id) if agent_id and agent_id.strip() else None,
        pipeline_mode=pipeline_mode == "on",
        status=TaskStatus.pending
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    agents = db.query(Agent).filter(Agent.is_active == True).all()
    projects = db.query(Project).all()
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()

    return templates.TemplateResponse(request, "partials/task_row.html", _ctx(request, lang, {
        "tasks": tasks, "agents": agents, "projects": projects
    }))


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user)
):
    init_db()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return HTMLResponse(content="")


@router.post("/{task_id}/run", response_class=HTMLResponse)
async def run_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == TaskStatus.running:
        raise HTTPException(status_code=400, detail="Task is already running")

    task.status = TaskStatus.pending
    db.commit()

    thread = threading.Thread(target=execute_task, args=(task_id,))
    thread.daemon = True
    thread.start()

    return templates.TemplateResponse(request, "partials/run_log.html", _ctx(request, lang, {
        "task_id": task_id,
        "message": "Task started. Check the Runs page for details."
    }))
