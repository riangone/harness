import subprocess
import threading
import os
import shlex
import re
import shutil
import logging
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session

from app.models import Task, Run, Agent, Project, TaskStatus, RunStatus, Schedule
from app.database import SessionLocal

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# 記憶サービス（遅延初期化シングルトン）
# ────────────────────────────────────────────────────────────────

_memory_service = None
_memory_lock = threading.Lock()


def _get_memory():
    """MemoryService のシングルトンを返す（遅延初期化）"""
    global _memory_service
    if _memory_service is None:
        with _memory_lock:
            if _memory_service is None:
                try:
                    from core.memory.service import MemoryService
                    _harness_root = os.path.abspath(
                        os.path.join(os.path.dirname(__file__), "..", "..", "..")
                    )
                    db_path = os.path.join(_harness_root, "data", "memory.db")
                    _memory_service = MemoryService(db_path)
                    logger.info(f"MemoryService 初期化完了: {db_path}")
                except Exception as e:
                    logger.warning(f"MemoryService 初期化失敗（記憶機能無効）: {e}")
                    return None
    return _memory_service

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


def _get_task_type(task: Task) -> str:
    """task_meta から task_type を読み取る"""
    if not task.task_meta:
        return 'general'
    try:
        import json
        meta = json.loads(task.task_meta) if isinstance(task.task_meta, str) else task.task_meta
        return meta.get('task_type', 'general')
    except Exception:
        return 'general'


def _collect_result(work_dir: str, task_type: str, run_log: str) -> str:
    """タスクタイプに応じた成果物ファイルを収集してresultにセット"""
    # タスクタイプ別の優先出力ファイル
    output_files = {
        'research':       ['report.md', 'output.md', 'result.md'],
        'writing':        ['output.md', 'draft.md', 'article.md', 'story.md'],
        'document':       ['document.md', 'slides.md', 'output.md', 'presentation.md'],
        'file_ops':       [],  # ファイル操作はログのみ
        'code_generation': [],  # コードはrun_logに含まれる
        'code_review':    ['review.md', 'output.md'],
        'bug_fix':        [],
        'general':        ['output.md', 'result.md'],
    }

    candidates = output_files.get(task_type, ['output.md', 'result.md'])
    for fname in candidates:
        fpath = os.path.join(work_dir, fname)
        content = _read_file(fpath)
        if content:
            return content

    # ファイルがなければrun_logの末尾2000文字
    if run_log:
        return run_log[-2000:] if len(run_log) > 2000 else run_log
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
    """Evaluator 用プロンプトを構築（タスクタイプ対応）"""
    task_type = _get_task_type(task)
    parts = []

    if agent.system_prompt:
        parts.append(agent.system_prompt)

    criteria_section = ""
    if task.success_criteria:
        criteria_section = f"""
## 成功基準
以下の基準をすべて満たしているか確認してください：

{task.success_criteria}

各基準について [x] または [ ] でチェックしてください。"""

    # タスクタイプ別評価基準
    type_checklist = {
        'code_generation': """- [x] 仕様通りに動作している
- [x] エッジケースが処理されている
- [x] セキュリティ上の問題なし
- [x] コードスタイルが適切""",
        'code_review': """- [x] セキュリティ問題を網羅的に確認した
- [x] 具体的な修正提案が含まれている
- [x] 優先度が明記されている""",
        'bug_fix': """- [x] 根本原因が特定・修正されている
- [x] 修正コードが動作する
- [x] リグレッションがない""",
        'research': """- [x] 調査内容が網羅的で正確
- [x] 情報源が明示されている（可能な場合）
- [x] 結論・提言が明確
- [x] 読みやすく構造化されている""",
        'writing': """- [x] 依頼内容に沿った内容
- [x] 文章の流れが自然で読みやすい
- [x] 誤字・脱字がない
- [x] 目的・ターゲットに合ったトーン""",
        'document': """- [x] 構成が論理的で見やすい
- [x] 内容が正確で過不足ない
- [x] 目的に合ったフォーマット""",
        'file_ops': """- [x] 指定されたファイル操作が完了している
- [x] データの損失がない
- [x] 操作結果が確認できる""",
        'general': """- [x] タスクの要求を満たしている
- [x] 成果物が明確に存在する
- [x] 品質が十分である""",
    }
    checklist = type_checklist.get(task_type, type_checklist['general'])

    parts.append(f"""以下の評価レポート形式で {work_dir}/eval-report.md に出力してください。

PASSの場合:
```markdown
# 評価レポート

VERDICT: PASS

## 確認事項
{checklist}
{criteria_section}
```

FAILの場合:
```markdown
# 評価レポート

VERDICT: FAIL

## 問題点
- ISSUE[1]: 問題の説明。具体的な修正指示
- ISSUE[2]: ...

## 修正優先度
HIGH: ISSUE[1]
MEDIUM: ISSUE[2]
```

必ず VERDICT: PASS または VERDICT: FAIL のいずれかを明記してください。""")

    if plan_content:
        parts.append(f"計画（plan.md）:\n\n{plan_content}")

    parts.append(f"評価対象タスク（タイプ: {task_type}）: {task.prompt}")

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


def _complete_task(db: Session, task: Task, result: str = None):
    """Task を completed に更新"""
    task.status = TaskStatus.completed
    task.updated_at = datetime.utcnow()
    if result:
        task.result = result
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
                      eval_content: str, attempt: int,
                      memory_context: str = "") -> str:
    """Generator 用プロンプトを構築（タスクタイプ対応・retry対応・記憶注入対応）"""
    task_type = _get_task_type(task)
    parts = []

    if agent.system_prompt:
        parts.append(agent.system_prompt)

    # 過去の成功経験を few-shot として注入（初回試行のみ）
    if memory_context and attempt == 1:
        parts.append(memory_context)

    if attempt > 1 and eval_content:
        parts.append(f"""前回の評価で以下の問題が指摘されています。必ず修正してください:

{eval_content}

上記の問題点をすべて修正して再度出力してください。""")
    elif attempt > 1:
        parts.append(f"前回の問題を修正して再実行してください。(試行 {attempt})")

    # タスクタイプ別の生成指示
    type_instructions = {
        'code_generation': "以下の計画に従ってコードを生成し、ファイルとして出力してください。",
        'code_review':     "以下の計画に従ってコードをレビューし、問題点と改善提案をまとめてください。",
        'bug_fix':         "以下の計画に従ってバグを修正したコードを出力してください。",
        'research':        "以下の調査計画に従って調査・情報収集を行い、report.md に構造化されたレポートを出力してください。",
        'writing':         "以下の執筆計画に従って文章を作成し、output.md に出力してください。",
        'document':        "以下の計画に従って資料・ドキュメントを作成し、document.md に出力してください。PPTのスライド内容ならMarkdown形式のスライド構成で記述してください。",
        'file_ops':        "以下の計画に従ってファイル・フォルダ操作を実行してください。",
        'general':         "以下の計画に従ってタスクを実行し、成果物を output.md に出力してください。",
    }
    instruction = type_instructions.get(task_type, type_instructions['general'])

    if plan_content:
        parts.append(f"""{instruction}

計画（plan.md）:
{plan_content}""")

    parts.append(f"タスク（タイプ: {task_type}）: {task.prompt}")

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

    記憶統合:
    - Planner: 過去のスキルテンプレート + プロジェクトコンテキストを注入
    - Generator: 過去の成功経験を few-shot で注入
    - PASS 時: スキル登録 + 成功経験保存
    - FAIL 時: 教訓抽出 + 失敗経験保存 + AGENTS.md 自動更新チェック
    """
    plan_file = os.path.join(work_dir, "plan.md")
    eval_file = os.path.join(work_dir, "eval-report.md")

    task_type = _get_task_type(task)
    memory = _get_memory()

    # ── プロジェクトコンテキストを収集（実プロジェクトディレクトリのみ）──
    project_context = ""
    try:
        from core.memory.auto_improve import collect_project_context
        project_context = collect_project_context(work_dir)
        if project_context:
            logger.info(f"プロジェクトコンテキスト収集完了: {len(project_context)} 文字")
    except Exception as e:
        logger.warning(f"プロジェクトコンテキスト収集失敗: {e}")

    # ── 過去スキルを取得（Planner 強化用）──
    past_skill = ""
    if memory:
        try:
            from core.memory.auto_improve import retrieve_skill
            past_skill = retrieve_skill(memory, task_type) or ""
            if past_skill:
                logger.info(f"過去スキル取得: task_type={task_type}")
        except Exception as e:
            logger.warning(f"スキル取得失敗: {e}")

    # ── 過去の成功経験を取得（Generator few-shot 用）──
    memory_context = ""
    if memory:
        try:
            memories = memory.retrieve_similar(task_type, limit=3, outcome_filter='success')
            if memories:
                memory_context = memory.build_context_from_memories(memories)
                logger.info(f"記憶 {len(memories)} 件を Generator に注入します")
        except Exception as e:
            logger.warning(f"記憶検索失敗: {e}")

    # Phase 1: Planning
    planner = _get_agents_by_role(db, "planner")
    if not planner:
        planner = _fallback_agent(db, "qwen")

    if not planner:
        _append_log(db, None, "[エラー] planner エージェントが見つかりません\n")
        _fail_task(db, task)
        return

    # タスクタイプ別プランナー指示
    plan_instructions = {
        'code_generation': f"コード実装計画を {plan_file} に出力してください。使用言語・設計方針・テスト計画を含めること。",
        'code_review':     f"レビュー計画を {plan_file} に出力してください。確認項目・重点領域・評価基準を含めること。",
        'bug_fix':         f"バグ修正計画を {plan_file} に出力してください。根本原因分析・修正手順・検証方法を含めること。",
        'research':        f"調査計画を {plan_file} に出力してください。調査項目・アプローチ・最終アウトプット形式を含めること。最終成果物は {work_dir}/report.md に出力する想定。",
        'writing':         f"執筆計画を {plan_file} に出力してください。構成・章立て・文体・文字数目安を含めること。最終成果物は {work_dir}/output.md に出力する想定。",
        'document':        f"資料作成計画を {plan_file} に出力してください。構成・セクション数・内容の概要を含めること。最終成果物は {work_dir}/document.md に出力する想定。",
        'file_ops':        f"ファイル操作計画を {plan_file} に出力してください。操作対象・手順・安全確認方法を含めること。",
        'general':         f"実行計画を {plan_file} に出力してください。手順・成果物・検証方法を含めること。最終成果物は {work_dir}/output.md に出力する想定。",
    }
    plan_instruction = plan_instructions.get(task_type, plan_instructions['general'])

    # プランナープロンプト（プロジェクトコンテキスト + 過去スキルを注入）
    planner_parts = []
    if planner.system_prompt:
        planner_parts.append(planner.system_prompt)
    if project_context:
        planner_parts.append(project_context)
    if past_skill:
        planner_parts.append(
            f"## 過去の成功計画テンプレート（参考）\n\n"
            f"以下は同種タスクで成功した計画の例です。参考にして今回の計画を立ててください:\n\n"
            f"```\n{past_skill}\n```"
        )
    planner_parts.append(f"タスク: {task.prompt}\n\n作業ディレクトリ: {work_dir}\n{plan_instruction}")
    planning_prompt = "\n\n".join(planner_parts)

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
    # Prefer qwen generator when available
    try:
        qwen_agent = next((a for a in generators if a.cli_command == "qwen"), None)
        if qwen_agent:
            generators = [qwen_agent] + [a for a in generators if a.id != qwen_agent.id]
    except Exception:
        pass
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

        # 記憶コンテキストは初回試行のみ注入（retry時は eval フィードバックを優先）
        gen_prompt = _build_gen_prompt(
            generator, task, plan_content, eval_content, attempt,
            memory_context=memory_context
        )

        gen_run = _create_run(db, task, generator, "generating", attempt=attempt)
        gen_success = _run_single_command(
            db, gen_run, _build_command(generator.cli_command, gen_prompt),
            work_dir, task
        )
        _finish_run(db, gen_run, gen_success)
        _update_agent_stats(db, generator, gen_run)

        if not gen_success:
            if attempt == 3:
                # 全試行失敗: 教訓を保存
                _store_failure_experience(memory, task_type, eval_content, attempt)
                _fail_task(db, task)
                return
            continue

        # Phase 3: Evaluation
        evaluator = _get_agents_by_role(db, "evaluator")
        if not evaluator:
            # Evaluator なしで完了
            _store_success_experience(memory, task_type, plan_content, generator.cli_command, attempt)
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
            # ── 成功: スキル登録 + 経験保存 ──
            _store_success_experience(memory, task_type, plan_content, generator.cli_command, attempt)
            result = _collect_result(work_dir, task_type, gen_run.log)
            _complete_task(db, task, result=result)
            return

        # FAIL: 教訓保存
        eval_content_full = _read_file(eval_file)
        _store_failure_experience(memory, task_type, eval_content_full, attempt)

        if attempt == 3:
            _fail_task(db, task)
            return

    _fail_task(db, task)


# ────────────────────────────────────────────────────────────────
# 経験保存ヘルパー
# ────────────────────────────────────────────────────────────────

def _store_success_experience(memory, task_type: str, plan_content: str,
                               generator_cli: str, attempt: int):
    """成功経験を記憶に保存してスキルを登録する"""
    if not memory:
        return
    try:
        from core.memory.auto_improve import register_skill
        register_skill(memory, task_type, plan_content, generator_cli, attempt)
        logger.info(f"成功経験を保存: task_type={task_type}, attempt={attempt}")
    except Exception as e:
        logger.warning(f"成功経験の保存に失敗: {e}")


def _store_failure_experience(memory, task_type: str, eval_content: str, attempt: int):
    """失敗経験を記憶に保存し、パターン蓄積時は AGENTS.md を自動更新する"""
    if not memory:
        return
    try:
        from core.memory.auto_improve import build_lesson, check_and_update_agents_md
        lesson = build_lesson(task_type, eval_content, attempt)
        memory.store_experience(
            task_type=task_type,
            outcome='failed',
            data={
                'lesson': lesson,
                'patterns': [],
                'tags': [task_type, f"attempt_{attempt}"],
            },
            agent_role='generator',
        )
        logger.info(f"失敗経験を保存: task_type={task_type}, attempt={attempt}")

        # 失敗が閾値を超えたら AGENTS.md を自動更新
        updated = check_and_update_agents_md(memory, task_type)
        if updated:
            logger.info(f"AGENTS.md を自動更新しました: task_type={task_type}")
    except Exception as e:
        logger.warning(f"失敗経験の保存に失敗: {e}")


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
