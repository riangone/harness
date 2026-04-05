from fastapi import APIRouter, Request, Form, Depends, HTTPException, Cookie
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.models import Project
from app.templates import templates
from app.auth import get_current_user
from app.i18n import get_lang, t as translate

router = APIRouter(prefix="/projects", tags=["projects"])


def _ctx(request: Request, lang: str | None, extra: dict = {}) -> dict:
    lang_code = get_lang(lang)
    ctx = {'lang': lang_code, 't': lambda key: translate(key, lang_code)}
    ctx.update(extra)
    return ctx


@router.get("", response_class=HTMLResponse)
async def projects_page(
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return templates.TemplateResponse(request, "projects.html", _ctx(request, lang, {"projects": projects}))


@router.get("/list", response_class=HTMLResponse)
async def projects_list(
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return templates.TemplateResponse(request, "partials/project_row.html", _ctx(request, lang, {"projects": projects}))


@router.post("", response_class=HTMLResponse)
async def create_project(
    request: Request,
    name: str = Form(...),
    path: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    init_db()
    project = Project(
        name=name,
        path=path,
        description=description
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return templates.TemplateResponse(request, "partials/project_row.html", _ctx(request, lang, {"projects": projects}))


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user)
):
    init_db()
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()
    return HTMLResponse(content="")
