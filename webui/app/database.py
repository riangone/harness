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
    seed_agents()


def seed_agents():
    from app.models import Agent, AgentRole
    db = SessionLocal()
    try:
        if db.query(Agent).count() > 0:
            return
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
