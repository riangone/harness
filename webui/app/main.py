from fastapi import FastAPI, Request, Cookie, Form, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional

from app.database import init_db
from app.routers import agents, projects, tasks, runs
from app.templates import templates
from app.auth import HARNESS_USER, HARNESS_PASSWORD, create_session_token, get_current_user
from app.i18n import get_lang, t as translate

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="Multi-AI Harness WebUI")


class UTF8Middleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if 'text/html' in response.headers.get('content-type', ''):
            response.headers['content-type'] = 'text/html; charset=utf-8'
        return response


app.add_middleware(UTF8Middleware)

# Initialize database
init_db()

# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


def get_template_context(request: Request, lang_cookie: str | None, extra: dict = {}) -> dict:
    lang = get_lang(lang_cookie)
    ctx = {'lang': lang, 't': lambda key: translate(key, lang)}
    ctx.update(extra)
    return ctx


# Include routers (auth is handled per-route below)
app.include_router(agents.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(runs.router)


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(os.path.join(BASE_DIR, "static", "favicon.ico"))


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": False})


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    if username == HARNESS_USER and password == HARNESS_PASSWORD:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="harness_session", value=create_session_token(username), httponly=True, max_age=60*60*24*7)
        return response
    return templates.TemplateResponse(request, "login.html", {"error": True}, status_code=401)


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="harness_session")
    return response


@app.post("/lang/{lang}")
async def set_lang(lang: str, request: Request):
    response = RedirectResponse(request.headers.get("referer", "/"), status_code=303)
    response.set_cookie("lang", lang, max_age=60*60*24*365)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: str = Depends(get_current_user),
    lang: str | None = Cookie(default=None)
):
    from app.database import get_db
    from app.models import Agent, Project, Task, Run

    db = next(get_db())
    try:
        agents_count = db.query(Agent).count()
        projects_count = db.query(Project).count()
        tasks_count = db.query(Task).count()
        recent_tasks = db.query(Task).order_by(Task.created_at.desc()).limit(5).all()
        recent_runs = db.query(Run).order_by(Run.started_at.desc()).limit(5).all()

        return templates.TemplateResponse(request, "index.html", get_template_context(request, lang, {
            "agents_count": agents_count,
            "projects_count": projects_count,
            "tasks_count": tasks_count,
            "recent_tasks": recent_tasks,
            "recent_runs": recent_runs
        }))
    finally:
        db.close()
