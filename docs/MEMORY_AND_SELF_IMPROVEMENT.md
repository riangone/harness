# 記憶システムと自己改善ループ

> 実装日: 2026-04-13  
> 対象バージョン: main (cffdb65)  
> 参考: [docs/借鉴HermesAgent的改进建议.md](./借鉴HermesAgent的改进建議.md)

---

## 概要

HermesAgent の「越用越聪明（使えば使うほど賢くなる）」設計を参考に、harness に以下の能力を実装した。

| 能力 | 実装前 | 実装後 |
|------|--------|--------|
| タスク間の学習 | なし（毎回ゼロから） | 成功経験を few-shot でプロンプト注入 |
| 失敗から学ぶ | 手動で AGENTS.md 更新 | eval-report.md を自動解析して保存 |
| ルールの自動化 | 人手維持 | 失敗3回で AGENTS.md に自動追記 |
| 計画の再利用 | なし | 成功した plan.md をスキルとして保存 |
| プロジェクト把握 | なし | README + ファイル構成を自動収集 |

---

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────┐
│                  executor.py (WebUI)                     │
│                                                         │
│  _execute_pipeline()                                    │
│       │                                                 │
│       ├─[起動時]─ collect_project_context()             │
│       │            └─ README.md + ディレクトリ構成      │
│       │                                                 │
│       ├─[起動時]─ retrieve_skill()                      │
│       │            └─ 同種タスクの過去成功 plan.md      │
│       │                                                 │
│       ├─[起動時]─ memory.retrieve_similar()             │
│       │            └─ 成功経験 few-shot コンテキスト    │
│       │                                                 │
│       ├─[Planner] ← project_context + past_skill 注入   │
│       ├─[Generator] ← memory_context (few-shot) 注入    │
│       ├─[Evaluator] → eval-report.md 生成               │
│       │                                                 │
│       ├─[PASS] → _store_success_experience()            │
│       │           ├─ register_skill()  [plan.md保存]    │
│       │           └─ memory.store_experience(success)   │
│       │                                                 │
│       └─[FAIL] → _store_failure_experience()            │
│                   ├─ build_lesson()   [教訓生成]        │
│                   ├─ memory.store_experience(failed)    │
│                   └─ check_and_update_agents_md()       │
│                       └─ 3回失敗で AGENTS.md 自動追記   │
└─────────────────────────────────────────────────────────┘
                          │ 読み書き
┌─────────────────────────▼───────────────────────────────┐
│              data/memory.db (SQLite)                     │
│                                                         │
│  memories テーブル                                       │
│  ├─ outcome: 'success' | 'failed'                       │
│  ├─ task_type: 'code_generation' | 'research' | ...     │
│  ├─ template: plan.md の内容 (success 時)               │
│  ├─ lesson:   失敗教訓テキスト (failed 時)              │
│  ├─ metrics:  attempt数・quality・generator CLI          │
│  └─ expires_at: 90日後に自動削除                        │
└─────────────────────────────────────────────────────────┘
```

---

## ファイル構成

```
core/memory/
├── __init__.py          # パッケージエクスポート
├── service.py           # MemoryService (SQLite CRUD)
├── compressor.py        # ContextCompressor (トークン制限対応)
└── auto_improve.py      # ★ 新規: 自動改善ロジック全般

webui/app/services/
└── executor.py          # ★ 改修: 記憶統合・自己改善ループ追加
```

---

## `core/memory/auto_improve.py` 詳細

### 教訓抽出

```python
from core.memory.auto_improve import extract_issues_from_eval, build_lesson

# eval-report.md から ISSUE[] を抽出
issues = extract_issues_from_eval(eval_content)
# → ["型アノテーションが欠落している", "エラーハンドリングがない"]

# 構造化された教訓テキストを生成
lesson = build_lesson("code_generation", eval_content, attempt=2)
# → "タスクタイプ [code_generation] attempt=2 で失敗した問題点:\n  - ..."
```

### スキル登録・取得

```python
from core.memory.auto_improve import register_skill, retrieve_skill

# PASS 後: plan.md をスキルとして保存
register_skill(memory, "code_generation", plan_content, "qwen", attempt=1)
# → quality="high" (attempt=1 の場合)
# → quality="medium" (attempt=2,3 の場合)

# 次回同種タスクの Planner 起動前に取得
past_plan = retrieve_skill(memory, "code_generation")
# → 過去の成功 plan.md テキスト (なければ None)
```

### AGENTS.md 自動更新

```python
from core.memory.auto_improve import check_and_update_agents_md

# 同一タスクタイプの失敗が3件以上あれば自動追記
updated = check_and_update_agents_md(memory, "code_generation")
# → True: AGENTS.md に追記された
# → False: まだ閾値未満 or 既にマーカーあり
```

追記される内容の例：

```markdown
---

<!-- [Auto][code_generation] 2026-04-13 15:30 -->

## code_generation 繰り返し失敗パターン（自動生成）

以下の問題が 3 回以上発生しています。次回から対策してください:

  1. タスクタイプ [code_generation] attempt=3 で失敗した問題点:
     - 型アノテーションが欠落している
  2. ...

*自動追記: 2026-04-13 15:30*
```

### プロジェクトコンテキスト収集

```python
from core.memory.auto_improve import collect_project_context

# プロジェクトディレクトリから README + ファイル構成を収集
ctx = collect_project_context("/path/to/project")
# /tmp/harness-* の一時ディレクトリは空文字を返す
```

収集される情報：

- `README.md` / `README.rst` / `README.txt` の先頭 800 文字
- トップレベルのファイル・ディレクトリ一覧（隠しファイル・`__pycache__` 除外）

---

## `executor.py` の変更点

### `_get_memory()` — 遅延初期化シングルトン

```python
memory = _get_memory()
# → MemoryService インスタンス (data/memory.db)
# → 初期化失敗時は None を返す（記憶機能を無効化してパイプラインは継続）
```

失敗時もパイプライン実行は止まらない。記憶機能は**オプション扱い**。

### `_build_gen_prompt()` — memory_context パラメータ追加

```python
gen_prompt = _build_gen_prompt(
    generator, task, plan_content, eval_content, attempt,
    memory_context=memory_context   # ← 追加
)
```

- `attempt == 1` かつ `memory_context` がある場合のみ few-shot を注入
- `attempt >= 2` は eval フィードバックを優先（記憶は注入しない）

### `_execute_pipeline()` — 記憶統合の全体フロー

```
起動時（1回だけ実行）:
  1. collect_project_context(work_dir)    → project_context
  2. retrieve_skill(memory, task_type)    → past_skill
  3. memory.retrieve_similar(task_type)  → memory_context (few-shot)

Planner プロンプト構成:
  [system_prompt]
  + [project_context]    ← 自動収集
  + [past_skill]         ← 過去の成功計画
  + [タスク本文 + 指示]

Generator プロンプト構成 (attempt=1):
  [system_prompt]
  + [memory_context]     ← 過去の成功経験 few-shot
  + [plan.md の内容]
  + [タスク本文]

Generator プロンプト構成 (attempt>=2):
  [system_prompt]
  + [eval-report.md のフィードバック]   ← 記憶なし
  + [plan.md の内容]
  + [タスク本文]
```

---

## データスキーマ

### memories テーブル（`data/memory.db`）

| カラム | 型 | 説明 |
|--------|-----|------|
| `id` | INTEGER | 主キー |
| `task_type` | TEXT | `code_generation` / `research` / `bug_fix` 等 |
| `agent_role` | TEXT | `generator` / `planner` 等 |
| `outcome` | TEXT | `success` または `failed` |
| `template` | TEXT (JSON) | 成功時: plan.md の内容 |
| `lesson` | TEXT | 失敗時: 教訓テキスト |
| `metrics` | TEXT (JSON) | `{attempt, quality, generator}` |
| `tags` | TEXT (JSON) | `["code_generation", "qwen", "high"]` 等 |
| `expires_at` | TIMESTAMP | 90日後（自動削除対象） |

### quality フィールドの意味

| 値 | 条件 | 意味 |
|----|------|------|
| `high` | attempt=1 で PASS | 一発で成功した高品質な計画 |
| `medium` | attempt=2,3 で PASS | 修正後に成功した計画 |

---

## 動作確認

```bash
# 単体テスト
python3 -c "
from core.memory.service import MemoryService
from core.memory.auto_improve import register_skill, retrieve_skill, build_lesson

mem = MemoryService('data/test.db')

# スキル登録
register_skill(mem, 'code_generation', '# 計画\n1. 実装\n2. テスト', 'qwen', 1)

# スキル取得
print(retrieve_skill(mem, 'code_generation'))

# 教訓生成
lesson = build_lesson('code_generation', 'ISSUE[1]: 型がない', 2)
print(lesson)
"
```

---

## 設計上の注意点

### 記憶の鮮度

- 保持期間: **90日**（`retention_days=90`）
- 期限切れは `memory.cleanup_expired()` で削除
- 古い記憶より新しい記憶が優先（`ORDER BY created_at DESC`）

### AGENTS.md 更新の冪等性

同一タスクタイプのマーカー `[Auto][{task_type}]` が既に存在する場合は追記しない。
手動で既存エントリを削除すれば次の閾値到達時に再追記される。

### フォールバック設計

`_get_memory()` が `None` を返した場合（import 失敗・DB 作成失敗等）、
`_store_success_experience()` / `_store_failure_experience()` はすべて
`if not memory: return` で早期リターンするため、**パイプライン実行は継続される**。

---

## 今後の拡張候補（HermesAgent 提案より未実装）

| 項目 | 優先度 | 概要 |
|------|--------|------|
| ベクトル類似検索 | Medium | SQLite FTS5 または ChromaDB で意味的な記憶検索 |
| LLM による教訓要約 | Medium | 複数 FAIL の共通パターンを LLM で抽象化 |
| ユーザーモデリング | Low | 送信者ごとの好みや成功パターンを蓄積 |
| 構造化トレース | Low | OpenTelemetry 形式でのパイプライン実行記録 |
| Telegram ゲートウェイ | Low | WebUI 以外からのタスク投入 |
