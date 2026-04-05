from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class AgentRole(str, Enum):
    planner = "planner"
    generator = "generator"
    evaluator = "evaluator"
    researcher = "researcher"


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class RunStatus(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


# Agent schemas
class AgentBase(BaseModel):
    name: str
    cli_command: str
    role: AgentRole
    system_prompt: str = ""
    is_active: bool = True


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    cli_command: Optional[str] = None
    role: Optional[AgentRole] = None
    system_prompt: Optional[str] = None
    is_active: Optional[bool] = None


class AgentResponse(AgentBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Project schemas
class ProjectBase(BaseModel):
    name: str
    path: str
    description: str = ""


class ProjectCreate(ProjectBase):
    pass


class ProjectResponse(ProjectBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Task schemas
class TaskBase(BaseModel):
    title: str
    prompt: str
    project_id: Optional[int] = None
    agent_id: Optional[int] = None
    pipeline_mode: bool = False


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    prompt: Optional[str] = None
    project_id: Optional[int] = None
    agent_id: Optional[int] = None
    pipeline_mode: Optional[bool] = None
    status: Optional[TaskStatus] = None


class TaskResponse(TaskBase):
    id: int
    status: TaskStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Run schemas
class RunBase(BaseModel):
    task_id: int
    agent_id: int
    phase: str = "planning"


class RunCreate(RunBase):
    pass


class RunResponse(RunBase):
    id: int
    status: RunStatus
    log: str = ""
    started_at: datetime
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True
