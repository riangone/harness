from fastapi import APIRouter, Request, Form, Depends, HTTPException, Cookie
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional
import threading
from app.models import Run

from app.database import get_db, init_db
from app.models import Task, TaskStatus, Agent, Project
from app.services.executor import execute_task, execute_parallel_tasks
from app.templates import templates
from app.auth import get_current_user, can_edit
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
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    agents = db.query(Agent).filter(Agent.is_active == True).all()
    projects = db.query(Project).all()
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    # 依存関係用のタスク一覧
    all_tasks = db.query(Task).all()
    return templates.TemplateResponse(request, "tasks.html", _ctx(request, lang, {
        "tasks": tasks, "agents": agents, "projects": projects, "all_tasks": all_tasks,
        "can_edit": can_edit(user), "user": user
    }))


@router.get("/list", response_class=HTMLResponse)
async def tasks_list(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    agents = db.query(Agent).filter(Agent.is_active == True).all()
    projects = db.query(Project).all()
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    all_tasks = db.query(Task).all()
    return templates.TemplateResponse(request, "partials/task_row.html", _ctx(request, lang, {
        "tasks": tasks, "agents": agents, "projects": projects, "all_tasks": all_tasks,
        "can_edit": can_edit(user), "user": user
    }))


@router.post("", response_class=HTMLResponse)
async def create_task(
    request: Request,
    title: str = Form(...),
    prompt: str = Form(...),
    success_criteria: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    agent_id: Optional[str] = Form(None),
    depends_on_id: Optional[str] = Form(None),
    parallel_group: Optional[str] = Form(None),
    pipeline_mode: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    if not can_edit(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    task = Task(
        title=title,
        prompt=prompt,
        success_criteria=success_criteria or "",
        project_id=int(project_id) if project_id and project_id.strip() else None,
        agent_id=int(agent_id) if agent_id and agent_id.strip() else None,
        depends_on_id=int(depends_on_id) if depends_on_id and depends_on_id.strip() else None,
        parallel_group=parallel_group if parallel_group and parallel_group.strip() else None,
        pipeline_mode=pipeline_mode == "on",
        status=TaskStatus.pending
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    agents = db.query(Agent).filter(Agent.is_active == True).all()
    projects = db.query(Project).all()
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    all_tasks = db.query(Task).all()

    return templates.TemplateResponse(request, "partials/task_row.html", _ctx(request, lang, {
        "tasks": tasks, "agents": agents, "projects": projects, "all_tasks": all_tasks,
        "can_edit": can_edit(user), "user": user
    }))


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    if not can_edit(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    init_db()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return HTMLResponse(content="")


@router.get("/{task_id}/edit", response_class=HTMLResponse)
async def edit_task_form(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    agents = db.query(Agent).filter(Agent.is_active == True).all()
    projects = db.query(Project).all()
    all_tasks = db.query(Task).filter(Task.id != task_id).all()
    return templates.TemplateResponse(request, "partials/task_edit_form.html", _ctx(request, lang, {
        "task": task, "agents": agents, "projects": projects, "all_tasks": all_tasks,
        "can_edit": can_edit(user), "user": user
    }))


@router.put("/{task_id}", response_class=HTMLResponse)
async def update_task(
    task_id: int,
    request: Request,
    title: str = Form(...),
    prompt: str = Form(...),
    success_criteria: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    agent_id: Optional[str] = Form(None),
    depends_on_id: Optional[str] = Form(None),
    parallel_group: Optional[str] = Form(None),
    pipeline_mode: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    if not can_edit(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    init_db()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.title = title
    task.prompt = prompt
    task.success_criteria = success_criteria or ""
    task.project_id = int(project_id) if project_id and project_id.strip() else None
    task.agent_id = int(agent_id) if agent_id and agent_id.strip() else None
    task.depends_on_id = int(depends_on_id) if depends_on_id and depends_on_id.strip() else None
    task.parallel_group = parallel_group if parallel_group and parallel_group.strip() else None
    task.pipeline_mode = pipeline_mode == "on"
    db.commit()
    db.refresh(task)

    agents = db.query(Agent).filter(Agent.is_active == True).all()
    projects = db.query(Project).all()
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    all_tasks = db.query(Task).all()
    return templates.TemplateResponse(request, "partials/task_row.html", _ctx(request, lang, {
        "tasks": tasks, "agents": agents, "projects": projects, "all_tasks": all_tasks,
        "can_edit": can_edit(user), "user": user
    }))


@router.post("/{task_id}/run", response_class=HTMLResponse)
async def run_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
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

    # 並列グループがある場合、同じグループのタスクをまとめて実行
    if task.parallel_group:
        parallel_tasks = db.query(Task).filter(
            Task.parallel_group == task.parallel_group,
            Task.id != task_id,
            Task.status == TaskStatus.pending
        ).all()
        task_ids = [task.id] + [t.id for t in parallel_tasks]
        execute_parallel_tasks(task_ids)
    else:
        thread = threading.Thread(target=execute_task, args=(task_id,))
        thread.daemon = True
        thread.start()

    lang_code = get_lang(lang)
    response = HTMLResponse(
        content=f'<span class="badge badge-running">{translate("running", lang_code)}...</span>'
    )
    response.headers["HX-Trigger"] = "reloadTaskList"
    return response
