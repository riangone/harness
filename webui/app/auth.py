import os
from itsdangerous import URLSafeSerializer
from fastapi import Cookie, HTTPException

SECRET_KEY = os.environ.get('HARNESS_SECRET', 'harness-secret-key-change-me')
HARNESS_USER = os.environ.get('HARNESS_USER', 'admin')
HARNESS_PASSWORD = os.environ.get('HARNESS_PASSWORD', 'admin')
serializer = URLSafeSerializer(SECRET_KEY)


def create_session_token(username: str) -> str:
    return serializer.dumps(username)


def verify_session_token(token: str) -> str | None:
    try:
        return serializer.loads(token)
    except Exception:
        return None


def get_current_user(session: str | None = Cookie(default=None, alias='harness_session')) -> str:
    if session:
        user = verify_session_token(session)
        if user:
            return user
    raise HTTPException(status_code=302, headers={'Location': '/login'})
