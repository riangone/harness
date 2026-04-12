from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.database import Base


class AgentRole(str, enum.Enum):
    planner = "planner"
    generator = "generator"
    evaluator = "evaluator"
    researcher = "researcher"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class RunStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    cli_command = Column(String(100), nullable=False)
    role = Column(Enum(AgentRole), nullable=False)
    system_prompt = Column(Text, nullable=True, default="")
    priority = Column(Integer, nullable=False, default=10)  # 数字が小さいほど優先
    is_active = Column(Boolean, nullable=False, default=True)
    total_runs = Column(Integer, nullable=False, default=0)  # 実行統計
    total_passes = Column(Integer, nullable=False, default=0)
    avg_duration_ms = Column(Integer, nullable=False, default=0)
    estimated_cost = Column(Integer, nullable=False, default=0)  # 概算コスト（token数）
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    tasks = relationship("Task", back_populates="agent", foreign_keys="Task.agent_id")
    runs = relationship("Run", back_populates="agent")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    path = Column(String(500), nullable=False)
    description = Column(Text, nullable=True, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    tasks = relationship("Task", back_populates="project")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    prompt = Column(Text, nullable=False)
    success_criteria = Column(Text, nullable=True, default="")  # スプリント契約
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    depends_on_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)  # タスク依存関係
    pipeline_mode = Column(Boolean, nullable=False, default=False)
    parallel_group = Column(String(100), nullable=True, default=None)  # 並列実行グループ
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.pending)
    source = Column(String(50), nullable=True, default="webui")  # 任务来源: webui/api/email
    result = Column(Text, nullable=True, default="")  # 任务执行结果
    task_meta = Column("metadata", Text, nullable=True, default=None)  # JSON 元数据（callback_url, from_addr 等）
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="tasks", foreign_keys=[project_id])
    agent = relationship("Agent", back_populates="tasks", foreign_keys=[agent_id])
    runs = relationship("Run", back_populates="task")
    dependency = relationship("Task", remote_side=[id], foreign_keys=[depends_on_id])
    dependent_tasks = relationship("Task", remote_side=[depends_on_id], foreign_keys=[depends_on_id])


class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    phase = Column(String(100), nullable=False, default="planning")
    attempt = Column(Integer, nullable=False, default=1)
    status = Column(Enum(RunStatus), nullable=False, default=RunStatus.running)
    eval_verdict = Column(String(20), nullable=True, default=None)
    tokens_estimated = Column(Integer, nullable=True, default=None)  # コスト追跡
    log = Column(Text, nullable=True, default="")
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    task = relationship("Task", back_populates="runs")
    agent = relationship("Agent", back_populates="runs")


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    cron_expression = Column(String(100), nullable=False)  # cron形式
    is_active = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    task = relationship("Task", foreign_keys=[task_id])


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="viewer")  # admin / editor / viewer
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
