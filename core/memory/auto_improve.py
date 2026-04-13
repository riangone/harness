"""
AutoImprove - 自動改善モジュール

失敗パターンを分析してAGENTS.mdを自動更新し、
成功パターンを「スキル」として蓄積・再利用する。

フロー:
  FAIL → extract_lesson() → store_experience(failed)
       → check threshold → append_rule_to_agents_md()
  PASS → register_skill() → store_experience(success)
       → 次回同種タスクで retrieve_skill() して planner に注入
"""

import re
import os
import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

# AGENTS.md はプロジェクトルートに置く
_HARNESS_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
AGENTS_MD_PATH = os.path.join(_HARNESS_ROOT, "AGENTS.md")

# 同一タスクタイプで何回失敗したらAGENTS.mdを更新するか
FAILURE_THRESHOLD = 3


# ────────────────────────────────────────────────────────────────
# 教訓抽出
# ────────────────────────────────────────────────────────────────

def extract_issues_from_eval(eval_content: str) -> List[str]:
    """eval-report.md の ISSUE[] を抽出する"""
    return re.findall(r'ISSUE\[\d+\]:\s*(.+)', eval_content)


def build_lesson(task_type: str, eval_content: str, attempt: int) -> str:
    """
    構造化された教訓文字列を生成する。

    Args:
        task_type: タスクタイプ (code_generation 等)
        eval_content: eval-report.md の全文
        attempt: 何回目の試行で失敗したか

    Returns:
        AGENTS.md に追記できる形式の教訓文字列
    """
    issues = extract_issues_from_eval(eval_content)
    if not issues:
        # ISSUE[] がなければ eval の冒頭を使う
        snippet = eval_content[:400].strip() if eval_content else "(eval-report なし)"
        return f"タスクタイプ [{task_type}] attempt={attempt} で失敗:\n  {snippet}"

    lines = [f"タスクタイプ [{task_type}] attempt={attempt} で失敗した問題点:"]
    for issue in issues:
        lines.append(f"  - {issue.strip()}")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────
# AGENTS.md 自動更新
# ────────────────────────────────────────────────────────────────

def check_and_update_agents_md(memory, task_type: str) -> bool:
    """
    同一 task_type の失敗が FAILURE_THRESHOLD 件以上蓄積していたら
    失敗パターンをまとめて AGENTS.md に追記する。

    Args:
        memory: MemoryService インスタンス
        task_type: タスクタイプ

    Returns:
        追記した場合 True
    """
    recent_failures = memory.retrieve_similar(
        task_type=task_type,
        limit=FAILURE_THRESHOLD + 2,
        outcome_filter='failed'
    )

    if len(recent_failures) < FAILURE_THRESHOLD:
        return False

    # すでに AGENTS.md にこのパターンが書き込まれているか確認
    existing = _read_agents_md()
    marker = f"[Auto][{task_type}]"
    if marker in existing:
        # 既存エントリがあれば過剰追記しない
        return False

    # 教訓を集約
    lessons = [
        f["lesson"] for f in recent_failures[:FAILURE_THRESHOLD]
        if f.get("lesson")
    ]
    if not lessons:
        return False

    rule = _aggregate_lessons(task_type, lessons)
    return _append_to_agents_md(marker, rule)


def _read_agents_md() -> str:
    try:
        with open(AGENTS_MD_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _aggregate_lessons(task_type: str, lessons: List[str]) -> str:
    """複数教訓をまとめてルール文字列に変換"""
    combined = "\n".join(f"  {i+1}. {l}" for i, l in enumerate(lessons))
    return (
        f"## {task_type} 繰り返し失敗パターン（自動生成）\n\n"
        f"以下の問題が {len(lessons)} 回以上発生しています。次回から対策してください:\n\n"
        f"{combined}\n"
    )


def _append_to_agents_md(marker: str, rule: str) -> bool:
    """AGENTS.md の末尾にルールを追記する"""
    if not os.path.exists(AGENTS_MD_PATH):
        logger.warning(f"AGENTS.md が見つかりません: {AGENTS_MD_PATH}")
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n\n---\n\n<!-- {marker} {timestamp} -->\n\n{rule}\n*自動追記: {timestamp}*\n"

    try:
        with open(AGENTS_MD_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.info(f"AGENTS.md を自動更新しました: {marker}")
        return True
    except Exception as e:
        logger.error(f"AGENTS.md の更新に失敗しました: {e}")
        return False


# ────────────────────────────────────────────────────────────────
# スキル登録 / 検索
# ────────────────────────────────────────────────────────────────

def register_skill(
    memory,
    task_type: str,
    plan_content: str,
    generator_cli: str,
    attempt: int
):
    """
    PASS したパイプラインの plan.md をスキルとして登録する。

    attempt=1 (一発成功) のものを高品質スキルとして優先保存。

    Args:
        memory: MemoryService インスタンス
        task_type: タスクタイプ
        plan_content: plan.md の内容
        generator_cli: 使用した generator の cli_command
        attempt: 成功した試行番号
    """
    if not plan_content:
        return

    quality = "high" if attempt == 1 else "medium"

    memory.store_experience(
        task_type=task_type,
        outcome="success",
        data={
            "template": plan_content[:2000],   # plan.md の先頭2000文字
            "metrics": {
                "attempt": attempt,
                "quality": quality,
                "generator": generator_cli,
            },
            "tags": [task_type, generator_cli, quality],
        },
        agent_role="generator",
    )
    logger.info(
        f"スキル登録: task_type={task_type}, quality={quality}, "
        f"generator={generator_cli}"
    )


def retrieve_skill(memory, task_type: str) -> Optional[str]:
    """
    同一タスクタイプの過去の成功 plan をスキルとして取得する。

    Returns:
        plan テンプレート文字列（なければ None）
    """
    memories = memory.retrieve_similar(
        task_type=task_type,
        role="generator",
        limit=1,
        outcome_filter="success",
    )
    if not memories:
        return None

    mem = memories[0]
    template = mem.get("template")
    if not template:
        return None

    # dict の場合は文字列化
    if isinstance(template, dict):
        import json
        return json.dumps(template, ensure_ascii=False, indent=2)
    return str(template)


# ────────────────────────────────────────────────────────────────
# プロジェクトコンテキスト収集
# ────────────────────────────────────────────────────────────────

def collect_project_context(work_dir: str, max_chars: int = 2000) -> str:
    """
    プロジェクトディレクトリから自動的にコンテキスト情報を収集する。

    収集内容:
    - README.md (先頭 800 文字)
    - トップレベルのファイル/ディレクトリ一覧

    /tmp/harness-* のような一時ディレクトリの場合は空文字を返す。

    Args:
        work_dir: プロジェクトの作業ディレクトリ
        max_chars: 最大文字数

    Returns:
        フォーマット済みコンテキスト文字列
    """
    if not work_dir or work_dir.startswith("/tmp/harness-"):
        return ""

    parts = []

    # README を収集
    for readme_name in ("README.md", "README.rst", "README.txt", "README"):
        readme_path = os.path.join(work_dir, readme_name)
        if os.path.exists(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(800)
                parts.append(f"## README\n```\n{content}\n```")
            except Exception:
                pass
            break

    # ファイル/ディレクトリ一覧（1階層のみ）
    try:
        entries = sorted(os.listdir(work_dir))
        # 隠しファイル・__pycache__ を除外
        visible = [
            e for e in entries
            if not e.startswith(".") and e != "__pycache__"
        ]
        dirs = [e + "/" for e in visible if os.path.isdir(os.path.join(work_dir, e))]
        files = [e for e in visible if os.path.isfile(os.path.join(work_dir, e))]
        tree = "\n".join(dirs + files)
        parts.append(f"## プロジェクト構成\n```\n{tree}\n```")
    except Exception:
        pass

    if not parts:
        return ""

    context = "# プロジェクトコンテキスト（自動収集）\n\n" + "\n\n".join(parts)
    return context[:max_chars]
