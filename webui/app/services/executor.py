import subprocess
import threading
import os
import shlex
import re
import shutil
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session

from app.models import Task, Run, Agent, Project, TaskStatus, RunStatus, Schedule
from app.database import SessionLocal

# ────────────────────────────────────────────────────────────────
# TaskExecutor: 実行中のタスクを追跡
# ────────────────────────────────────────────────────────────────

class TaskExecutor:
    """実行中のタスクを追跡する"""
    _running_tasks: dict[int, subprocess.Popen] = {}
    _lock = threading.Lock()
    _thread_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="parallel-")

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

    @classmethod
    def submit_parallel(cls, task_id: int):
        """並列実行グループのタスクをスレッドプールに投入"""
        cls._thread_pool.submit(execute_task, task_id)


# ────────────────────────────────────────────────────────────────
# ユーティリティ
# ────────────────────────────────────────────────────────────────

def _append_log(db: Session, run: Run, text: str):
    """Runログに追記"""
    run.log = (run.log or "") + text
    db.commit()


def _build_env() -> dict:
    """CLIが見つかるようにPATHを拡張した環境変数を返す"""
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
    """CLIコマンドをリスト形式で構築する（shell=Falseで安全に実行）"""
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


def _read_file(path: str) -> str:
    """ファイルを読んで文字列で返す。存在しない場合は空文字"""
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception:
        pass
    return ""


def _parse_verdict(eval_file: str) -> str:
    """eval-report.md を読んで PASS / FAIL / UNKNOWN を返す"""
    content = _read_file(eval_file)
    if not content:
        return "UNKNOWN"
    match = re.search(r'VERDICT:\s*(PASS|FAIL)', content, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return "UNKNOWN"


# ────────────────────────────────────────────────────────────────
# エージェントヘルスチェック
# ────────────────────────────────────────────────────────────────

def _check_cli_available(cli_command: str) -> bool:
    """CLIが存在し実行可能か確認する"""
    if cli_command == 'gh-copilot':
        return shutil.which('gh') is not None
    return shutil.which(cli_command) is not None


def _get_agents_by_role(db: Session, role: str) -> Optional[Agent]:
    """指定されたロールの有効エージェントをpriority順で取得。ヘルスチェック済み"""
    agents = db.query(Agent).filter(
        Agent.role == role,
        Agent.is_active == True
    ).order_by(Agent.priority.asc()).all()

    for agent in agents:
        if _check_cli_available(agent.cli_command):
            return agent
    return None


def _get_agents_by_role_all(db: Session, role: str) -> list[Agent]:
    """指定ロールの有効エージェントを priority 昇順で全件返す（ヘルスチェック済み）"""
    agents = db.query(Agent).filter(
        Agent.role == role,
        Agent.is_active == True
    ).order_by(Agent.priority.asc()).all()

    return [a for a in agents if _check_cli_available(a.cli_command)]


def _fallback_agent(db: Session, cli_command: str) -> Optional[Agent]:
    """指定CLIの代替エージェントを取得"""
    return db.query(Agent).filter(
        Agent.cli_command == cli_command,
        Agent.is_active == True
    ).first()


# ────────────────────────────────────────────────────────────────
# 実行統計の更新
# ────────────────────────────────────────────────────────────────

def _update_agent_stats(db: Session, agent: Agent, run: Run):
    """エージェントの実行統計を更新する"""
    agent.total_runs += 1

    if run.status == RunStatus.completed and run.eval_verdict == "PASS":
        agent.total_passes += 1

    if run.started_at and run.finished_at:
        duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
        # 移動平均で更新
        agent.avg_duration_ms = int(
            (agent.avg_duration_ms * (agent.total_runs - 1) + duration_ms) / agent.total_runs
        )

    if run.tokens_estimated:
        agent.estimated_cost += run.tokens_estimated

    db.commit()


# ────────────────────────────────────────────────────────────────
# スプリント契約（成功基準）
# ────────────────────────────────────────────────────────────────

def _build_eval_prompt(agent: Agent, task: Task, plan_content: str, work_dir: str) -> str:
    """Evaluator 用プロンプトを構築（success_criteria を含む）"""
    parts = []

    if agent.system_prompt:
        parts.append(agent.system_prompt)

    criteria_section = ""
    if task.success_criteria:
        criteria_section = f"""
## スプリント契約（成功基準）
以下の基準をすべて満たしているか確認してください：

{task.success_criteria}

各基準について [x] または [ ] でチェックしてください。"""

    parts.append(f"""以下の評価レポート形式で {work_dir}/eval-report.md に出力してください。

```markdown
# 評価レポート

VERDICT: PASS または FAIL

## 確認事項（PASSの場合）
- [x] 仕様通りに動作している
- [x] エッジケースが処理されている
- [x] セキュリティ上の問題なし
{criteria_section}
```

失敗の場合:
```markdown
# 評価レポート

VERDICT: FAIL

## 問題点
- ISSUE[1]: ファイル:行 — 問題の説明。具体的な修正指示
- ISSUE[2]: ...

## 修正優先度
HIGH: ISSUE[1], ISSUE[2]
MEDIUM: ISSUE[3]
```

必ず VERDICT: PASS または VERDICT: FAIL のいずれかを明記してください。""")

    if plan_content:
        parts.append(f"""実装計画（plan.md）の内容:

{plan_content}""")

    parts.append(f"評価対象タスク: {task.prompt}")

    return "\n\n".join(parts)


# ────────────────────────────────────────────────────────────────
# Run / Task 管理
# ────────────────────────────────────────────────────────────────

def _create_run(
    db: Session,
    task: Task,
    agent: Agent,
    phase: str,
    attempt: int = 1
) -> Run:
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


def _finish_run(db: Session, run: Run, success: bool):
    """Run を completed / failed で閉じる"""
    run.finished_at = datetime.utcnow()
    run.status = RunStatus.completed if success else RunStatus.failed
    db.commit()


def _fail_task(db: Session, task: Task):
    """Task を failed に更新"""
    task.status = TaskStatus.failed
    task.updated_at = datetime.utcnow()
    db.commit()


def _complete_task(db: Session, task: Task):
    """Task を completed に更新"""
    task.status = TaskStatus.completed
    task.updated_at = datetime.utcnow()
    db.commit()


# ────────────────────────────────────────────────────────────────
# 単一コマンド実行
# ────────────────────────────────────────────────────────────────

def _run_single_command(
    db: Session,
    run: Run,
    command: list[str],
    work_dir: str,
    task: Task
) -> bool:
    """単一コマンドを実行。成功したらTrue"""
    try:
        cmd_display = ' '.join(shlex.quote(c) for c in command)
        _append_log(db, run, f"\n--- 実行コマンド: {cmd_display}\n--- 作業ディレクトリ: {work_dir}\n\n")
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

        TaskExecutor.register(task.id, process)

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


# ────────────────────────────────────────────────────────────────
# Generator / Planner プロンプト構築
# ────────────────────────────────────────────────────────────────

def _build_gen_prompt(agent: Agent, task: Task, plan_content: str,
                      eval_content: str, attempt: int) -> str:
    """Generator 用プロンプトを構築（retry 時は eval-report.md の問題点を含める）"""
    parts = []

    if agent.system_prompt:
        parts.append(agent.system_prompt)

    if attempt > 1 and eval_content:
        parts.append(f"""前回の評価で以下の問題が指摘されています。必ず修正してください:

{eval_content}

上記の問題点をすべて修正した実装を出力してください。""")
    elif attempt > 1:
        parts.append(f"前回の問題を修正して実装してください。(試行 {attempt})")

    if plan_content:
        parts.append(f"""以下の実装計画に従ってコードを生成してください:

{plan_content}""")

    parts.append(f"タスク: {task.prompt}")

    return "\n\n".join(parts)


# ────────────────────────────────────────────────────────────────
# タスク依存関係チェック
# ────────────────────────────────────────────────────────────────

def _check_dependency(db: Session, task: Task) -> bool:
    """依存タスクが完了しているか確認。依存タスクがなければ True"""
    if not task.depends_on_id:
        return True

    dep_task = db.query(Task).filter(Task.id == task.depends_on_id).first()
    if not dep_task:
        return True

    if dep_task.status == TaskStatus.completed:
        return True

    # 依存タスクが failed なら即失敗
    if dep_task.status == TaskStatus.failed:
        return False

    # 依存タスクが実行中でなければ実行する
    if dep_task.status in (TaskStatus.pending,):
        _append_log(None, None, f"[依存] 依存タスク '{dep_task.title}' を先に実行します...\n")
        # 依存タスクを再帰的に実行
        execute_task(dep_task.id)
        # 再確認
        dep_task = db.query(Task).filter(Task.id == task.depends_on_id).first()
        return dep_task.status == TaskStatus.completed

    return False


# ────────────────────────────────────────────────────────────────
# メイン実行関数
# ────────────────────────────────────────────────────────────────

def execute_task(task_id: int):
    """タスクをバックグラウンドで実行するメイン関数"""
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return

        # 依存関係チェック
        if not _check_dependency(db, task):
            dep = db.query(Task).filter(Task.id == task.depends_on_id).first()
            task.status = TaskStatus.failed
            db.commit()
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
        db2 = SessionLocal()
        try:
            task = db2.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.failed
                db2.commit()
        finally:
            db2.close()
    finally:
        db.close()


def _execute_single(db: Session, task: Task, work_dir: str):
    """単一エージェント実行"""
    agent: Optional[Agent] = None

    if task.agent_id:
        agent = db.query(Agent).filter(Agent.id == task.agent_id).first()
        # ヘルスチェック
        if agent and not _check_cli_available(agent.cli_command):
            _append_log(db, None, f"[ヘルスチェック] {agent.cli_command} が見つかりません。フォールバックします。\n")
            agent = None

    if not agent:
        agent = db.query(Agent).filter(
            Agent.cli_command == "qwen",
            Agent.is_active == True
        ).first()

    if not agent:
        task.status = TaskStatus.failed
        db.commit()
        return

    run = _create_run(db, task, agent, "execution")

    system_prompt = agent.system_prompt or ""
    full_prompt = f"{system_prompt}\n\n{task.prompt}".strip() if system_prompt else task.prompt

    # success_criteria があれば prompt に追加
    if task.success_criteria:
        full_prompt += f"\n\n## 成功基準\n{task.success_criteria}"

    command = _build_command(agent.cli_command, full_prompt)

    success = _run_single_command(db, run, command, work_dir, task)

    _finish_run(db, run, success)
    _update_agent_stats(db, agent, run)

    task.status = TaskStatus.completed if success else TaskStatus.failed
    db.commit()


def _execute_pipeline(db: Session, task: Task, work_dir: str):
    """
    パイプライン実行: planner → generator → evaluator
    コンテキスト分離: ファイル（plan.md, eval-report.md）のみをフェーズ間で受け渡し
    """
    plan_file = os.path.join(work_dir, "plan.md")
    eval_file = os.path.join(work_dir, "eval-report.md")

    # Phase 1: Planning
    planner = _get_agents_by_role(db, "planner")
    if not planner:
        planner = _fallback_agent(db, "qwen")

    if not planner:
        _append_log(db, None, "[エラー] planner エージェントが見つかりません\n")
        _fail_task(db, task)
        return

    planning_prompt = f"""{planner.system_prompt or ''}

タスク: {task.prompt}

作業ディレクトリ {plan_file} に詳細な実装計画を出力してください。"""

    planning_run = _create_run(db, task, planner, "planning", attempt=1)
    planning_success = _run_single_command(
        db, planning_run, _build_command(planner.cli_command, planning_prompt),
        work_dir, task
    )
    _finish_run(db, planning_run, planning_success)
    _update_agent_stats(db, planner, planning_run)

    if not planning_success:
        _fail_task(db, task)
        return

    # Phase 2: Generation + Evaluation loop (最大3回)
    generators = _get_agents_by_role_all(db, "generator")
    if not generators:
        qwen = _fallback_agent(db, "qwen")
        if qwen:
            generators = [qwen]

    if not generators:
        _fail_task(db, task)
        return

    for attempt in range(1, 4):
        generator = generators[min(attempt - 1, len(generators) - 1)]

        plan_content = _read_file(plan_file)
        eval_content = _read_file(eval_file) if attempt > 1 else ""

        gen_prompt = _build_gen_prompt(generator, task, plan_content, eval_content, attempt)

        gen_run = _create_run(db, task, generator, "generating", attempt=attempt)
        gen_success = _run_single_command(
            db, gen_run, _build_command(generator.cli_command, gen_prompt),
            work_dir, task
        )
        _finish_run(db, gen_run, gen_success)
        _update_agent_stats(db, generator, gen_run)

        if not gen_success:
            if attempt == 3:
                _fail_task(db, task)
                return
            continue

        # Phase 3: Evaluation
        evaluator = _get_agents_by_role(db, "evaluator")
        if not evaluator:
            _complete_task(db, task)
            return

        eval_prompt = _build_eval_prompt(evaluator, task, plan_content, work_dir)

        eval_run = _create_run(db, task, evaluator, "evaluating", attempt=attempt)
        eval_success = _run_single_command(
            db, eval_run, _build_command(evaluator.cli_command, eval_prompt),
            work_dir, task
        )
        _finish_run(db, eval_run, eval_success)
        _update_agent_stats(db, evaluator, eval_run)

        verdict = _parse_verdict(eval_file)
        eval_run.eval_verdict = verdict
        db.commit()

        if verdict == "PASS":
            _complete_task(db, task)
            return

        if attempt == 3:
            _fail_task(db, task)
            return

    _fail_task(db, task)


# ────────────────────────────────────────────────────────────────
# 並列実行
# ────────────────────────────────────────────────────────────────

def execute_parallel_tasks(task_ids: list[int]):
    """複数のタスクを並列実行"""
    for task_id in task_ids:
        TaskExecutor.submit_parallel(task_id)


# ────────────────────────────────────────────────────────────────
# スケジュール実行管理
# ────────────────────────────────────────────────────────────────

def _parse_cron(cron_expr: str) -> dict:
    """cron 式をパース（分 時 日 月 曜日）"""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return None
    return {
        'minute': parts[0],
        'hour': parts[1],
        'day': parts[2],
        'month': parts[3],
        'weekday': parts[4]
    }


def _cron_matches(cron: dict, dt: datetime) -> bool:
    """datetime が cron 式と一致するか判定"""
    def match_field(pattern: str, value: int) -> bool:
        if pattern == '*':
            return True
        if ',' in pattern:
            return str(value) in pattern.split(',')
        if '-' in pattern:
            start, end = pattern.split('-')
            return int(start) <= value <= int(end)
        if '/' in pattern:
            base, step = pattern.split('/')
            if base == '*':
                return value % int(step) == 0
            return (value - int(base)) % int(step) == 0
        return str(value) == pattern

    return (match_field(cron['minute'], dt.minute) and
            match_field(cron['hour'], dt.hour) and
            match_field(cron['day'], dt.day) and
            match_field(cron['month'], dt.month) and
            match_field(cron['weekday'], dt.weekday()))


def check_and_run_schedules():
    """スケジュールを確認し、実行時刻になったタスクを実行"""
    from datetime import datetime
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        schedules = db.query(Schedule).filter(Schedule.is_active == True).all()

        for schedule in schedules:
            cron = _parse_cron(schedule.cron_expression)
            if not cron:
                continue

            if _cron_matches(cron, now):
                # 実行
                task = db.query(Task).filter(Task.id == schedule.task_id).first()
                if task and task.status != TaskStatus.running:
                    # 新しい Task を作成して実行
                    new_task = Task(
                        title=f"[scheduled] {task.title}",
                        prompt=task.prompt,
                        success_criteria=task.success_criteria,
                        project_id=task.project_id,
                        agent_id=task.agent_id,
                        pipeline_mode=task.pipeline_mode,
                        status=TaskStatus.pending,
                    )
                    db.add(new_task)
                    db.commit()
                    db.refresh(new_task)

                    schedule.last_run_at = now
                    db.commit()

                    # バックグラウンドで実行
                    thread = threading.Thread(target=execute_task, args=(new_task.id,))
                    thread.daemon = True
                    thread.start()

    finally:
        db.close()
