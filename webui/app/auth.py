import os
import hashlib
from itsdangerous import URLSafeSerializer
from fastapi import Cookie, HTTPException

from app.database import SessionLocal
from app.models import User

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


def authenticate_user(username: str, password: str) -> User | None:
    """ユーザー名とパスワードで認証（DBベース）"""
    # 環境変数のフォールバック
    if username == HARNESS_USER and password == HARNESS_PASSWORD:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username).first()
            if user and user.is_active:
                return user
        finally:
            db.close()
        return None

    # DB ベース認証
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    db = SessionLocal()
    try:
        user = db.query(User).filter(
            User.username == username,
            User.password_hash == password_hash,
            User.is_active == True
        ).first()
        return user
    finally:
        db.close()


def get_user_by_username(username: str) -> User | None:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.username == username).first()
    finally:
        db.close()


def get_current_user(session: str | None = Cookie(default=None, alias='harness_session')) -> User:
    """現在のユーザーを取得（RBAC対応）"""
    if session:
        username = verify_session_token(session)
        if username:
            user = get_user_by_username(username)
            if user:
                return user
    raise HTTPException(status_code=302, headers={'Location': '/login'})


def require_role(required_role: str):
    """指定ロール以上の権限が必要かチェックするデペンデンシー"""
    role_hierarchy = {'viewer': 0, 'editor': 1, 'admin': 2}

    def role_checker(user: User = get_current_user) -> User:
        if role_hierarchy.get(user.role, 0) < role_hierarchy.get(required_role, 0):
            raise HTTPException(status_code=403, detail="権限が不足しています")
        return user

    return role_checker


def can_edit(user: User) -> bool:
    return user.role in ('editor', 'admin')


def can_admin(user: User) -> bool:
    return user.role == 'admin'
