"""
pipeline_executor.py — Multi-AI Harness 独立执行 API

供外部系统（如 MailMind）调用 Harness 的多角色管道能力，
无需启动 Web UI 即可使用 planner → generator → evaluator 流水线。

用法：
    from app.pipeline_executor import run_pipeline

    result = run_pipeline(
        prompt="实现一个 TODO App，支持增删改查",
        work_dir="/tmp/my-task",
        pipeline_mode="full"  # 或 "single"
    )
    print(result["status"])  # "completed" 或 "failed"
    print(result["output"])  # 完整日志
"""

import subprocess
import threading
import os
import shlex
import re
import sys
from datetime import datetime
from typing import Optional, Dict, Any

# 确保能导入 app 模块
_harness_webui_dir = os.path.dirname(os.path.abspath(__file__))
if _harness_webui_dir not in sys.path:
    sys.path.insert(0, _harness_webui_dir)

from app.database import SessionLocal, init_db
from app.models import Agent, AgentRole, Task, Run, TaskStatus, RunStatus


# ────────────────────────────────────────────────────────────────
# 公开 API: run_pipeline
# ────────────────────────────────────────────────────────────────

def run_pipeline(
    prompt: str,
    work_dir: Optional[str] = None,
    pipeline_mode: str = "full",
    project_name: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    执行 Harness 多 AI 管道。

    参数:
        prompt: 任务描述（自然语言）
        work_dir: 工作目录（可选，默认 /tmp/harness-pipeline-<timestamp>）
        pipeline_mode: "full" (planner→generator→evaluator) 或 "single" (单 AI)
        project_name: 项目名称（用于日志归档，可选）
        timeout: 超时秒数（可选，默认不限制）

    返回:
        {
            "status": "completed" | "failed",
            "output": "完整执行日志（含命令、输出、评估结果）",
            "work_dir": "实际工作目录",
            "task_id": Harness 内部 Task ID（可选，用于追踪）,
        }
    """
    if not work_dir:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        work_dir = f"/tmp/harness-pipeline-{ts}"
    os.makedirs(work_dir, exist_ok=True)

    db = SessionLocal()
    try:
        # 确保 DB 初始化 + Agent 播种
        init_db()

        # 创建临时 Task 记录
        task = Task(
            title=project_name or prompt[:50],
            prompt=prompt,
            project_id=None,
            agent_id=None,
            pipeline_mode=(pipeline_mode == "full"),
            status=TaskStatus.pending,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        result = {"task_id": task.id, "work_dir": work_dir}

        if pipeline_mode == "full":
            success = _execute_pipeline(db, task, work_dir, timeout=timeout)
        else:
            success = _execute_single(db, task, work_dir, timeout=timeout)

        result["status"] = "completed" if success else "failed"

        # 读取完整日志
        runs = db.query(Run).filter(Run.task_id == task.id).order_by(Run.id).all()
        log_parts = []
        for run in runs:
            log_parts.append(f"\n{'='*60}\n")
            log_parts.append(f"[Phase: {run.phase}] [Agent ID: {run.agent_id}] [Attempt: {run.attempt}]")
            if run.eval_verdict:
                log_parts.append(f"[Verdict: {run.eval_verdict}]")
            log_parts.append(f"{'='*60}\n\n")
            log_parts.append(run.log or "")

            # 读取产出文件
            if run.phase == "planning":
                plan_file = os.path.join(work_dir, "plan.md")
                if os.path.exists(plan_file):
                    log_parts.append(f"\n\n--- plan.md 内容 ---\n{_read_file(plan_file)}")
            elif run.phase in ("generating", "execution"):
                # 列出工作目录的文件
                try:
                    files = os.listdir(work_dir)
                    log_parts.append(f"\n\n--- 产出文件列表: {', '.join(files)} ---")
                except Exception:
                    pass
            elif run.phase == "evaluating":
                eval_file = os.path.join(work_dir, "eval-report.md")
                if os.path.exists(eval_file):
                    log_parts.append(f"\n\n--- eval-report.md 内容 ---\n{_read_file(eval_file)}")

        result["output"] = "".join(log_parts)
        return result

    except Exception as e:
        return {
            "status": "failed",
            "output": f"[异常] {str(e)}",
            "work_dir": work_dir,
            "task_id": None,
        }
    finally:
        db.close()


# ────────────────────────────────────────────────────────────────
# 内部执行逻辑（从 executor.py 抽取并简化）
# ────────────────────────────────────────────────────────────────

_running_tasks: dict[int, subprocess.Popen] = {}
_lock = threading.Lock()


def _build_env() -> dict:
    """CLI 路径扩展"""
    env = os.environ.copy()
    extra_paths = [
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/bin"),
        "/usr/local/bin",
    ]
    nvm_dir = os.path.expanduser("~/.nvm/versions/node")
    if os.path.isdir(nvm_dir):
        for ver in sorted(os.listdir(nvm_dir), reverse=True):
            extra_paths.append(os.path.join(nvm_dir, ver, "bin"))
            break
    current_path = env.get("PATH", "")
    for p in extra_paths:
        if p not in current_path:
            current_path = p + os.pathsep + current_path
    env["PATH"] = current_path
    return env


def _build_command(cli_command: str, prompt: str) -> list[str]:
    """构建安全命令列表"""
    if cli_command == 'gh-copilot':
        return ['gh', 'copilot', 'suggest', '-t', 'shell', prompt]
    if cli_command == 'claude':
        return ['claude', '-p', prompt, '--dangerously-skip-permissions']
    if cli_command == 'qwen':
        return ['qwen', '-y', prompt]
    if cli_command == 'gemini':
        return ['gemini', '-p', prompt]
    if cli_command == 'codex':
        return ['codex', 'exec', prompt]
    return [cli_command, prompt]


def _run_single_command(
    db, run, command: list[str], work_dir: str,
    timeout: Optional[int] = None
) -> bool:
    """执行单条命令，实时写入日志"""
    try:
        cmd_display = ' '.join(shlex.quote(c) for c in command)
        run.log = (run.log or "") + f"\n--- 执行命令: {cmd_display}\n--- 工作目录: {work_dir}\n\n"
        db.commit()

        process = subprocess.Popen(
            command,
            shell=False,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=_build_env()
        )

        with _lock:
            _running_tasks[run.task_id] = process

        if process.stdout:
            for line in process.stdout:
                run.log = (run.log or "") + line
                db.commit()

        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            run.log = (run.log or "") + f"\n[超时] 命令执行超过 {timeout} 秒\n"
            db.commit()
            return False

        with _lock:
            _running_tasks.pop(run.task_id, None)

        if process.returncode == 0:
            return True
        else:
            run.log = (run.log or "") + f"\n[错误] 命令退出码: {process.returncode}\n"
            db.commit()
            return False

    except Exception as e:
        run.log = (run.log or "") + f"\n[异常] {str(e)}\n"
        db.commit()
        with _lock:
            _running_tasks.pop(run.task_id, None)
        return False


def _get_agent_by_role(db, role: str):
    """获取指定角色优先级最高的 Agent"""
    return db.query(Agent).filter(
        Agent.role == role,
        Agent.is_active == True
    ).order_by(Agent.priority.asc()).first()


def _get_all_generators(db) -> list:
    """获取所有 generator Agent"""
    return db.query(Agent).filter(
        Agent.role == AgentRole.generator,
        Agent.is_active == True
    ).order_by(Agent.priority.asc()).all()


def _read_file(path: str) -> str:
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception:
        pass
    return ""


def _parse_verdict(eval_file: str) -> str:
    content = _read_file(eval_file)
    if not content:
        return "UNKNOWN"
    match = re.search(r'VERDICT:\s*(PASS|FAIL)', content, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return "UNKNOWN"


def _create_run(db, task, agent, phase: str, attempt: int = 1) -> Run:
    run = Run(
        task_id=task.id,
        agent_id=agent.id,
        phase=phase,
        attempt=attempt,
        status=RunStatus.running,
        log="",
        started_at=datetime.utcnow()
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _finish_run(db, run, success: bool):
    run.finished_at = datetime.utcnow()
    run.status = RunStatus.completed if success else RunStatus.failed
    db.commit()


def _execute_single(db, task, work_dir, timeout=None) -> bool:
    """单 AI 执行"""
    agent = db.query(Agent).filter(
        Agent.cli_command == "qwen",
        Agent.is_active == True
    ).first()

    if not agent:
        task.status = TaskStatus.failed
        db.commit()
        return False

    run = _create_run(db, task, agent, "execution")
    full_prompt = f"{agent.system_prompt}\n\n{task.prompt}".strip() if agent.system_prompt else task.prompt
    command = _build_command(agent.cli_command, full_prompt)

    success = _run_single_command(db, run, command, work_dir, timeout=timeout)

    _finish_run(db, run, success)
    task.status = TaskStatus.completed if success else TaskStatus.failed
    db.commit()
    return success


def _execute_pipeline(db, task, work_dir, timeout=None) -> bool:
    """管道执行: planner → generator → evaluator（最多 3 轮）"""
    plan_file = os.path.join(work_dir, "plan.md")
    eval_file = os.path.join(work_dir, "eval-report.md")

    # Phase 1: Planning
    planner = _get_agent_by_role(db, "planner")
    if not planner:
        planner = db.query(Agent).filter(
            Agent.cli_command == "claude",
            Agent.is_active == True
        ).first()

    if not planner:
        task.status = TaskStatus.failed
        db.commit()
        return False

    planning_prompt = f"""{planner.system_prompt or ''}

任务: {task.prompt}

请在 {plan_file} 输出详细实现计划。"""

    planning_run = _create_run(db, task, planner, "planning", attempt=1)
    planning_ok = _run_single_command(
        db, planning_run, _build_command(planner.cli_command, planning_prompt),
        work_dir, timeout=timeout
    )
    _finish_run(db, planning_run, planning_ok)
    if not planning_ok:
        task.status = TaskStatus.failed
        db.commit()
        return False

    # Phase 2: Generation + Evaluation loop
    generators = _get_all_generators(db)
    if not generators:
        qwen = db.query(Agent).filter(
            Agent.cli_command == "qwen",
            Agent.is_active == True
        ).first()
        if qwen:
            generators = [qwen]

    if not generators:
        task.status = TaskStatus.failed
        db.commit()
        return False

    for attempt in range(1, 4):
        generator = generators[min(attempt - 1, len(generators) - 1)]

        plan_content = _read_file(plan_file)
        eval_content = _read_file(eval_file) if attempt > 1 else ""

        # 构建 Generator prompt
        gen_parts = []
        if generator.system_prompt:
            gen_parts.append(generator.system_prompt)
        if attempt > 1 and eval_content:
            gen_parts.append(f"""上次评估发现以下问题，请务必修正：

{eval_content}

请输出修正后的完整实现。""")
        if plan_content:
            gen_parts.append(f"""请根据以下实现计划执行：

{plan_content}""")
        gen_parts.append(f"任务: {task.prompt}")

        gen_prompt = "\n\n".join(gen_parts)

        gen_run = _create_run(db, task, generator, "generating", attempt=attempt)
        gen_ok = _run_single_command(
            db, gen_run, _build_command(generator.cli_command, gen_prompt),
            work_dir, timeout=timeout
        )
        _finish_run(db, gen_run, gen_ok)

        if not gen_ok:
            if attempt == 3:
                task.status = TaskStatus.failed
                db.commit()
                return False
            continue

        # Phase 3: Evaluation
        evaluator = _get_agent_by_role(db, "evaluator")
        if not evaluator:
            # 没有 evaluator 就直接通过
            task.status = TaskStatus.completed
            db.commit()
            return True

        eval_prompt = f"""{evaluator.system_prompt or ''}

请评估以下实现，并将评估结果输出到 {eval_file}。

评估报告格式：
```markdown
# 评估报告

VERDICT: PASS 或 FAIL

## 问题点（仅 FAIL 时）
- ISSUE[1]: 文件:行 — 问题描述 + 具体修正指示
```

实现计划（plan.md）：
{plan_content}

任务: {task.prompt}

请务必在文件第一行写明 VERDICT: PASS 或 VERDICT: FAIL。"""

        eval_run = _create_run(db, task, evaluator, "evaluating", attempt=attempt)
        eval_ok = _run_single_command(
            db, eval_run, _build_command(evaluator.cli_command, eval_prompt),
            work_dir, timeout=timeout
        )
        _finish_run(db, eval_run, eval_ok)

        verdict = _parse_verdict(eval_file)
        eval_run.eval_verdict = verdict
        db.commit()

        if verdict == "PASS":
            task.status = TaskStatus.completed
            db.commit()
            return True

        if attempt == 3:
            task.status = TaskStatus.failed
            db.commit()
            return False
        # FAIL → 下一轮修正

    task.status = TaskStatus.failed
    db.commit()
    return False
