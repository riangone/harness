from fastapi import APIRouter, Request, Form, Depends, HTTPException, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
import hashlib
from datetime import datetime

from app.database import get_db, init_db
from app.models import User
from app.templates import templates
from app.auth import get_current_user, can_admin, authenticate_user, create_session_token
from app.i18n import get_lang, t as translate

router = APIRouter(prefix="/users", tags=["users"])


def _ctx(request: Request, lang: str | None, extra: dict = {}) -> dict:
    lang_code = get_lang(lang)
    ctx = {'lang': lang_code, 't': lambda key: translate(key, lang_code)}
    ctx.update(extra)
    return ctx


@router.get("", response_class=HTMLResponse)
async def users_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    if not can_admin(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    init_db()
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(request, "users.html", _ctx(request, lang, {
        "users": users, "user": user
    }))


@router.get("/list", response_class=HTMLResponse)
async def users_list(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    if not can_admin(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    init_db()
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(request, "partials/user_row.html", _ctx(request, lang, {
        "users": users
    }))


@router.post("", response_class=HTMLResponse)
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("viewer"),
    is_active: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    if not can_admin(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    init_db()
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    new_user = User(
        username=username,
        password_hash=password_hash,
        role=role,
        is_active=is_active == "on"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(request, "partials/user_row.html", _ctx(request, lang, {
        "users": users
    }))


@router.post("/{user_id}/toggle", response_class=HTMLResponse)
async def toggle_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    if not can_admin(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    init_db()
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.is_active = not target.is_active
    db.commit()

    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(request, "partials/user_row.html", _ctx(request, lang, {
        "users": users
    }))


@router.put("/{user_id}/role", response_class=HTMLResponse)
async def update_user_role(
    user_id: int,
    request: Request,
    role: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    if not can_admin(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    if role not in ('admin', 'editor', 'viewer'):
        raise HTTPException(status_code=400, detail="Invalid role")

    init_db()
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.role = role
    db.commit()

    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(request, "partials/user_row.html", _ctx(request, lang, {
        "users": users
    }))


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    if not can_admin(user):
        raise HTTPException(status_code=403, detail="権限が不足しています")

    # 自分は削除できない
    if user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    init_db()
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(target)
    db.commit()
    return HTMLResponse(content="")
