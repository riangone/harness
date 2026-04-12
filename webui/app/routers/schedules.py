from fastapi import APIRouter, Request, Form, Depends, HTTPException, Cookie
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db, init_db
from app.models import Schedule, Task
from app.templates import templates
from app.auth import get_current_user, can_edit
from app.i18n import get_lang, t as translate

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _ctx(request: Request, lang: str | None, extra: dict = {}) -> dict:
    lang_code = get_lang(lang)
    ctx = {'lang': lang_code, 't': lambda key: translate(key, lang_code)}
    ctx.update(extra)
    return ctx


@router.get("", response_class=HTMLResponse)
async def schedules_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    schedules = db.query(Schedule).order_by(Schedule.created_at.desc()).all()
    tasks = db.query(Task).all()
    return templates.TemplateResponse(request, "schedules.html", _ctx(request, lang, {
        "schedules": schedules, "tasks": tasks,
        "can_edit": can_edit(user), "user": user
    }))


@router.get("/list", response_class=HTMLResponse)
async def schedules_list(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    schedules = db.query(Schedule).order_by(Schedule.created_at.desc()).all()
    tasks = {t.id: t for t in db.query(Task).all()}
    return templates.TemplateResponse(request, "partials/schedule_row.html", _ctx(request, lang, {
        "schedules": schedules, "tasks": tasks
    }))


@router.post("", response_class=HTMLResponse)
async def create_schedule(
    request: Request,
    task_id: int = Form(...),
    cron_expression: str = Form(...),
    is_active: Optional[str] = Form(None),
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

    schedule = Schedule(
        task_id=task_id,
        cron_expression=cron_expression,
        is_active=is_active == "on"
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    schedules = db.query(Schedule).order_by(Schedule.created_at.desc()).all()
    tasks = db.query(Task).all()
    return templates.TemplateResponse(request, "partials/schedule_row.html", _ctx(request, lang, {
        "schedules": schedules, "tasks": tasks
    }))


@router.post("/{schedule_id}/toggle", response_class=HTMLResponse)
async def toggle_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    if not can_edit(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    init_db()
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule.is_active = not schedule.is_active
    db.commit()

    schedules = db.query(Schedule).order_by(Schedule.created_at.desc()).all()
    tasks = {t.id: t for t in db.query(Task).all()}
    return templates.TemplateResponse(request, "partials/schedule_row.html", _ctx(request, lang, {
        "schedules": schedules, "tasks": tasks
    }))


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    if not can_edit(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    init_db()
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    db.delete(schedule)
    db.commit()
    return HTMLResponse(content="")
