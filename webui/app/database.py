from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "harness.db")

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    migrate_runs_table()
    migrate_tasks_table()
    migrate_agents_table()
    create_schedules_table()
    create_users_table()
    seed_agents()
    seed_admin_user()


def migrate_runs_table():
    """runsテーブルにattemptとeval_verdictカラムを追加するマイグレーション"""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # attempt カラム確認
        cursor.execute("PRAGMA table_info(runs)")
        columns = [row[1] for row in cursor.fetchall()]
        if "attempt" not in columns:
            cursor.execute("ALTER TABLE runs ADD COLUMN attempt INTEGER DEFAULT 1")
        if "eval_verdict" not in columns:
            cursor.execute("ALTER TABLE runs ADD COLUMN eval_verdict TEXT")
        if "tokens_estimated" not in columns:
            cursor.execute("ALTER TABLE runs ADD COLUMN tokens_estimated INTEGER")
        conn.commit()
    finally:
        conn.close()


def migrate_tasks_table():
    """tasksテーブルに新カラムを追加するマイグレーション"""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(tasks)")
        columns = [row[1] for row in cursor.fetchall()]
        if "success_criteria" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN success_criteria TEXT DEFAULT ''")
        if "depends_on_id" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN depends_on_id INTEGER")
        if "parallel_group" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN parallel_group TEXT")
        conn.commit()
    finally:
        conn.close()


def migrate_agents_table():
    """agentsテーブルに統計カラムを追加するマイグレーション"""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(agents)")
        columns = [row[1] for row in cursor.fetchall()]
        for col in ["total_runs", "total_passes", "avg_duration_ms", "estimated_cost"]:
            if col not in columns:
                cursor.execute(f"ALTER TABLE agents ADD COLUMN {col} INTEGER DEFAULT 0")
        conn.commit()
    finally:
        conn.close()


def create_schedules_table():
    """schedulesテーブルを作成"""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(schedules)")
        if not cursor.fetchall():
            cursor.execute("""
                CREATE TABLE schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    cron_expression TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    last_run_at DATETIME,
                    next_run_at DATETIME,
                    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            """)
            conn.commit()
    finally:
        conn.close()


def create_users_table():
    """usersテーブルを作成"""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(users)")
        if not cursor.fetchall():
            cursor.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                    last_login_at DATETIME
                )
            """)
            conn.commit()
    finally:
        conn.close()


def seed_agents():
    from app.models import Agent, AgentRole
    db = SessionLocal()
    try:
        if db.query(Agent).count() > 0:
            return
    finally:
        db.close()

    db = SessionLocal()
    try:
        seeds = [
            Agent(name='Claude Planner', cli_command='claude', role=AgentRole.planner, priority=10, system_prompt='仕様策定・タスク分解を担当します。', is_active=True),
            Agent(name='Qwen Generator', cli_command='qwen', role=AgentRole.generator, priority=10, system_prompt='コード生成・実装を担当します。', is_active=True),
            Agent(name='Claude Evaluator', cli_command='claude', role=AgentRole.evaluator, priority=10, system_prompt='コードレビュー・品質評価を担当します。問題があれば具体的な修正箇所を指摘してください。', is_active=True),
            Agent(name='Gemini Researcher', cli_command='gemini', role=AgentRole.researcher, priority=10, system_prompt='大規模調査・Web検索を担当します。', is_active=True),
            Agent(name='Gemini Bug Fixer', cli_command='gemini', role=AgentRole.generator, priority=5, system_prompt='バグ修正に特化します。根本原因を分析して修正してください。', is_active=True),
            Agent(name='Codex Generator', cli_command='codex', role=AgentRole.generator, priority=15, system_prompt='コード生成の補助を担当します。', is_active=True),
            Agent(name='GitHub Copilot', cli_command='gh-copilot', role=AgentRole.generator, priority=20, system_prompt='GitHub Copilot CLIを使ったコード提案を担当します。', is_active=True),
        ]
        for s in seeds:
            db.add(s)
        db.commit()
    finally:
        db.close()


def seed_admin_user():
    """デフォルト admin ユーザーを作成（環境変数ベースの認証と互換）"""
    import sqlite3
    import hashlib
    from app.auth import HARNESS_USER, HARNESS_PASSWORD
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] > 0:
            return
        password_hash = hashlib.sha256(HARNESS_PASSWORD.encode()).hexdigest()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, 'admin', 1)",
            (HARNESS_USER, password_hash)
        )
        conn.commit()
    finally:
        conn.close()
