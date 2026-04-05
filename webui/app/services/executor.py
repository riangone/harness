import subprocess
import threading
import os
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Task, Run, Agent, Project, TaskStatus, RunStatus
from app.database import SessionLocal


class TaskExecutor:
    """実行中のタスクを追跡する"""
    _running_tasks: dict[int, subprocess.Popen] = {}
    _lock = threading.Lock()

    @classmethod
    def is_running(cls, task_id: int) -> bool:
        with cls._lock:
            return task_id in cls._running_tasks

    @classmethod
    def register(cls, task_id: int, process: subprocess.Popen):
        with cls._lock:
            cls._running_tasks[task_id] = process

    @classmethod
    def unregister(cls, task_id: int):
        with cls._lock:
            cls._running_tasks.pop(task_id, None)

    @classmethod
    def cancel(cls, task_id: int) -> bool:
        with cls._lock:
            proc = cls._running_tasks.get(task_id)
            if proc:
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                except Exception:
                    pass
                return True
            return False


def _append_log(db: Session, run: Run, text: str):
    """Runログに追記"""
    run.log = (run.log or "") + text
    db.commit()


def _build_command(cli_command: str, work_dir: str, prompt: str) -> str:
    """CLIコマンドを構築する"""
    if cli_command == 'gh-copilot':
        return f'cd {work_dir} && gh copilot suggest -t shell "{prompt}"'
    return f'cd {work_dir} && {cli_command} --yolo "{prompt}"'


def _run_single_command(
    db: Session,
    run: Run,
    command: str,
    work_dir: str,
    task: Task
) -> bool:
    """単一コマンドを実行。成功したらTrue"""
    try:
        _append_log(db, run, f"\n--- 実行コマンド: {command}\n--- 作業ディレクトリ: {work_dir}\n\n")
        db.commit()

        process = subprocess.Popen(
            command,
            shell=True,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        TaskExecutor.register(task.id, process)

        # リアルタイムでログを読み取り
        if process.stdout:
            for line in process.stdout:
                _append_log(db, run, line)

        process.wait()
        TaskExecutor.unregister(task.id)

        if process.returncode == 0:
            return True
        else:
            _append_log(db, run, f"\n[エラー] コマンドが終了コード {process.returncode} で終了しました\n")
            return False

    except Exception as e:
        _append_log(db, run, f"\n[例外] {str(e)}\n")
        TaskExecutor.unregister(task.id)
        return False


def _get_agents_by_role(db: Session, role: str) -> Optional[Agent]:
    """指定されたロールの有効エージェントをpriority順で取得"""
    return db.query(Agent).filter(
        Agent.role == role,
        Agent.is_active == True
    ).order_by(Agent.priority.asc()).first()


def _create_run(
    db: Session,
    task: Task,
    agent: Agent,
    phase: str
) -> Run:
    run = Run(
        task_id=task.id,
        agent_id=agent.id,
        phase=phase,
        status=RunStatus.running,
        log="",
        started_at=datetime.utcnow()
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_task(task_id: int):
    """タスクをバックグラウンドで実行するメイン関数"""
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return

        task.status = TaskStatus.running
        db.commit()

        project: Optional[Project] = None
        work_dir: str = ""

        if task.project_id:
            project = db.query(Project).filter(Project.id == task.project_id).first()

        if project and project.path:
            work_dir = project.path
            if not os.path.exists(work_dir):
                os.makedirs(work_dir, exist_ok=True)
        else:
            work_dir = f"/tmp/harness-{task_id}"
            os.makedirs(work_dir, exist_ok=True)

        if task.pipeline_mode:
            _execute_pipeline(db, task, work_dir)
        else:
            _execute_single(db, task, work_dir)

    except Exception as e:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.failed
            db.commit()
    finally:
        db.close()


def _execute_single(db: Session, task: Task, work_dir: str):
    """単一エージェント実行"""
    agent: Optional[Agent] = None

    if task.agent_id:
        agent = db.query(Agent).filter(Agent.id == task.agent_id).first()
    else:
        # デフォルト: qwen
        agent = db.query(Agent).filter(
            Agent.cli_command == "qwen",
            Agent.is_active == True
        ).first()

    if not agent:
        # 利用可能なエージェントがいない場合
        task.status = TaskStatus.failed
        db.commit()
        return

    run = _create_run(db, task, agent, "execution")

    system_prompt = agent.system_prompt or ""
    full_prompt = f"{system_prompt}\n\n{task.prompt}".strip() if system_prompt else task.prompt

    command = _build_command(agent.cli_command, work_dir, full_prompt)

    success = _run_single_command(db, run, command, work_dir, task)

    run.finished_at = datetime.utcnow()
    run.status = RunStatus.completed if success else RunStatus.failed
    db.commit()

    task.status = TaskStatus.completed if success else TaskStatus.failed
    db.commit()


def _execute_pipeline(db: Session, task: Task, work_dir: str):
    """パイプライン実行: planner → generator → evaluator (最大3回)"""

    # Phase 1: Planning
    planner = _get_agents_by_role(db, "planner")
    if not planner:
        # plannerがいなければqwenで代用
        planner = db.query(Agent).filter(
            Agent.cli_command == "qwen",
            Agent.is_active == True
        ).first()

    if not planner:
        task.status = TaskStatus.failed
        db.commit()
        return

    planning_run = _create_run(db, task, planner, "planning")
    planning_prompt = f"{planner.system_prompt or ''}\n\n以下の仕様を策定してください:\n{task.prompt}".strip()
    planning_cmd = _build_command(planner.cli_command, work_dir, planning_prompt)

    planning_success = _run_single_command(db, planning_run, planning_cmd, work_dir, task)
    planning_run.finished_at = datetime.utcnow()
    planning_run.status = RunStatus.completed if planning_success else RunStatus.failed
    db.commit()

    if not planning_success:
        task.status = TaskStatus.failed
        db.commit()
        return

    # Phase 2: Generation (最大3回の再試行ループ)
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        generator = _get_agents_by_role(db, "generator")
        if not generator:
            generator = db.query(Agent).filter(
                Agent.cli_command == "qwen",
                Agent.is_active == True
            ).first()

        if not generator:
            task.status = TaskStatus.failed
            db.commit()
            return

        gen_run = _create_run(db, task, generator, f"generating (attempt {attempt})")
        gen_prompt = f"{generator.system_prompt or ''}\n\n".strip()

        if attempt > 1:
            gen_prompt += f"前回の問題を修正して実装してください。(試行 {attempt}/{max_retries})\n\n"

        gen_prompt += task.prompt

        gen_cmd = _build_command(generator.cli_command, work_dir, gen_prompt)

        gen_success = _run_single_command(db, gen_run, gen_cmd, work_dir, task)
        gen_run.finished_at = datetime.utcnow()
        gen_run.status = RunStatus.completed if gen_success else RunStatus.failed
        db.commit()

        if not gen_success:
            if attempt == max_retries:
                task.status = TaskStatus.failed
                db.commit()
                return
            continue

        # Phase 3: Evaluation
        evaluator = _get_agents_by_role(db, "evaluator")
        if not evaluator:
            # evaluatorがいなければ完了とする
            task.status = TaskStatus.completed
            db.commit()
            return

        eval_run = _create_run(db, task, evaluator, f"evaluating (attempt {attempt})")
        eval_prompt = f"{evaluator.system_prompt or ''}\n\n以下の実装を評価してください。問題がある場合は改善点を列挙してください:\n{task.prompt}".strip()
        eval_cmd = _build_command(evaluator.cli_command, work_dir, eval_prompt)

        eval_success = _run_single_command(db, eval_run, eval_cmd, work_dir, task)
        eval_run.finished_at = datetime.utcnow()
        eval_run.status = RunStatus.completed if eval_success else RunStatus.failed
        db.commit()

        if eval_success:
            task.status = TaskStatus.completed
            db.commit()
            return

        # 評価で問題があった場合は再試行
        if attempt == max_retries:
            task.status = TaskStatus.failed
            db.commit()
            return
