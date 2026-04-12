from fastapi import APIRouter, Request, Form, Depends, HTTPException, Cookie
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db, init_db
from app.models import Agent, AgentRole
from app.templates import templates
from app.auth import get_current_user, can_admin
from app.i18n import get_lang, t as translate

router = APIRouter(prefix="/agents", tags=["agents"])


def _ctx(request: Request, lang: str | None, extra: dict = {}) -> dict:
    lang_code = get_lang(lang)
    ctx = {'lang': lang_code, 't': lambda key: translate(key, lang_code)}
    ctx.update(extra)
    return ctx


@router.get("", response_class=HTMLResponse)
async def agents_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    agents = db.query(Agent).order_by(Agent.priority.asc()).all()
    return templates.TemplateResponse(request, "agents.html", _ctx(request, lang, {
        "agents": agents, "can_admin": can_admin(user), "user": user
    }))


@router.get("/list", response_class=HTMLResponse)
async def agents_list(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    agents = db.query(Agent).order_by(Agent.priority.asc()).all()
    return templates.TemplateResponse(request, "partials/agent_row.html", _ctx(request, lang, {
        "agents": agents, "can_admin": can_admin(user), "user": user
    }))


@router.get("/stats", response_class=HTMLResponse)
async def agents_stats(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    """エージェントの実行統計を表示"""
    init_db()
    agents = db.query(Agent).order_by(Agent.total_runs.desc()).all()
    return templates.TemplateResponse(request, "partials/agent_stats.html", _ctx(request, lang, {
        "agents": agents
    }))


@router.post("", response_class=HTMLResponse)
async def create_agent(
    request: Request,
    name: str = Form(...),
    cli_command: str = Form(...),
    role: str = Form(...),
    system_prompt: str = Form(""),
    priority: int = Form(10),
    is_active: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    try:
        agent_role = AgentRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    agent = Agent(
        name=name,
        cli_command=cli_command,
        role=agent_role,
        system_prompt=system_prompt,
        priority=priority,
        is_active=is_active == "on"
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    agents = db.query(Agent).order_by(Agent.priority.asc()).all()
    return templates.TemplateResponse(request, "partials/agent_row.html", _ctx(request, lang, {
        "agents": agents, "can_admin": can_admin(user), "user": user
    }))


@router.get("/{agent_id}/edit", response_class=HTMLResponse)
async def edit_agent_form(
    agent_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return templates.TemplateResponse(request, "partials/agent_edit_form.html", _ctx(request, lang, {
        "agent": agent
    }))


@router.put("/{agent_id}", response_class=HTMLResponse)
async def update_agent(
    agent_id: int,
    request: Request,
    name: str = Form(...),
    cli_command: str = Form(...),
    role: str = Form(...),
    system_prompt: str = Form(""),
    priority: int = Form(10),
    is_active: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        agent_role = AgentRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    agent.name = name
    agent.cli_command = cli_command
    agent.role = agent_role
    agent.system_prompt = system_prompt
    agent.priority = priority
    agent.is_active = is_active == "on"
    db.commit()
    db.refresh(agent)

    agents = db.query(Agent).order_by(Agent.priority.asc()).all()
    return templates.TemplateResponse(request, "partials/agent_row.html", _ctx(request, lang, {
        "agents": agents, "can_admin": can_admin(user), "user": user
    }))


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    if not can_admin(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    db.delete(agent)
    db.commit()
    return HTMLResponse(content="")


@router.post("/{agent_id}/reset-stats", response_class=HTMLResponse)
async def reset_agent_stats(
    agent_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    """エージェントの統計をリセット"""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.total_runs = 0
    agent.total_passes = 0
    agent.avg_duration_ms = 0
    agent.estimated_cost = 0
    db.commit()

    agents = db.query(Agent).order_by(Agent.priority.asc()).all()
    return templates.TemplateResponse(request, "partials/agent_row.html", _ctx(request, lang, {
        "agents": agents, "can_admin": can_admin(user), "user": user
    }))
