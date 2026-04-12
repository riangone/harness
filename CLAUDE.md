# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## このプロジェクトの役割

Claude はこのハーネスの **司令塔・評価者** である。
大量生成・定型実装は Qwen に委託し、Claude は判断・評価・設計に集中する。

## タスク振り分け原則

- 定型コード生成 → **Qwen を使う（優先）**
- 大規模調査 → Gemini を使う
- 設計・評価・ハーネス改善 → Claude が担当

## コマンド

### WebUI 起動（ポート 10000）
```bash
cd webui && bash start.sh
# または（PYTHONPATH 設定が必要）
export PYTHONPATH=/home/ubuntu/ws/harness:/home/ubuntu/ws/harness/webui:$PYTHONPATH
uvicorn app.main:app --host 0.0.0.0 --port 10000 --reload --app-dir webui
```

### スタンドアロン API サーバー（ポート 7500）
```bash
python3 harness_api.py
# または uvicorn harness_api:app --host 0.0.0.0 --port 7500 --reload
```

### テスト実行
```bash
python3 tests/test_core.py                   # Core 2.0 統合テスト（6モジュール）
python3 test_mail_parse.py                   # メール解析テスト
python3 tests/test_quick_integration.py
```

### DB マイグレーション
```bash
bash scripts/migrate_db.sh
```

## 環境変数

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `HARNESS_SECRET` | `harness-secret-key-change-me` | セッションシリアライザ秘密鍵 |
| `HARNESS_USER` | `admin` | 環境変数ベース認証ユーザー名 |
| `HARNESS_PASSWORD` | `admin` | 環境変数ベース認証パスワード |
| `HARNESS_API_TOKEN` | （未設定 = 認証なし） | 外部 API Token（未設定は開発モード） |

## アーキテクチャ概要

```
MailMindHub（メール収発）
    ↓ POST /api/v1/tasks/from-email
Harness HTTP API（harness_api.py / webui/app/routers/external_api.py）
    ↓
WebUI（FastAPI: webui/app/main.py）
    ├── routers/  → agents / projects / tasks / runs / schedules / users / external_api
    ├── services/executor.py  → CLI 実行・Pipeline 制御・並列実行・統計更新
    └── harness.db（SQLite: webui/harness.db）

Core 2.0 モジュール（core/）
    ├── models/registry.py   → YAML 駆動モデル選択・Fallback チェーン
    ├── memory/service.py    → SQLite 経験蓄積・few-shot 検索
    ├── pipeline/engine.py   → YAML 定義パイプライン実行・条件分岐
    ├── gateway/mail.py      → メール内容解析と応答フォーマット（SMTP 送受信は行わない）
    └── orchestrator.py      → 統一エントリーポイント

設定ファイル（config/）: models.yaml / gateway.yaml / memory.yaml
Pipeline テンプレート（templates/）: code_generation / code_review / bug_fix / default
```

**重要な設計決定**: harness は SMTP/IMAP を含まない純粋な編排カーネル。メール送受信は MailMindHub が担う。harness は HTTP API を通じてサービスを提供し、タスク完了後は Webhook でコールバックする（ポーリング不要）。

## Pipeline 実行フロー

```
タスク作成（WebUI または POST /api/v1/tasks）
    ↓ pipeline_mode = true の場合
1. Planner エージェント → plan.md 生成
2. Generator エージェント（priority 順、最大3回 retry）→ 実装
3. Evaluator エージェント → eval-report.md（PASS/FAIL 判定）
    ↓ FAIL → Generator に eval-report.md を渡して再試行
    ↓ PASS → callback_url に Webhook 送信（MailMindHub 通知）
```

スケジューラはバックグラウンドスレッドで60秒ごとに実行される（`main.py` で起動、`executor.check_and_run_schedules()` を呼ぶ）。

## 重要なファイル

| 用途 | パス |
|------|------|
| Task 実行制御（核心） | `webui/app/services/executor.py` |
| ORM モデル定義 | `webui/app/models.py` |
| 外部 API・メール連携 | `webui/app/routers/external_api.py` |
| DB 初期化・マイグレーション | `webui/app/database.py` |
| 認証・RBAC | `webui/app/auth.py` |
| Core メールゲートウェイ | `core/gateway/mail.py` |
| Pipeline エンジン | `core/pipeline/engine.py` |

## DB スキーマ（主要テーブル）

- **Agent**: `cli_command`・`role`（planner/generator/evaluator/researcher）・`priority`（小＝高優先）・実行統計
- **Task**: `prompt`・`success_criteria`・`pipeline_mode`・`depends_on_id`・`parallel_group`・`source`（webui/api/email）・`task_meta`（JSON: callback_url, from_addr 等）
- **Run**: `phase`・`attempt`・`eval_verdict`・`log`（SSE ストリーミング対応）
- **User**: `username`・`password_hash`（SHA-256）・`role`（admin/editor/viewer）

初期シード: `admin/admin` ユーザー（DB ベース）、7種デフォルトエージェント（`database.py`）

## 評価時の基準

成果物を評価する際は以下を確認すること：
1. 仕様通りに動作しているか（スタブ・モック禁止）
2. エッジケースが処理されているか
3. セキュリティ上の問題がないか
4. 具体的な修正箇所を示しているか

## ミス発生時のフロー

1. ミスの根本原因を分析
2. `AGENTS.md` に再発防止ルールを追記
3. 次のタスクに反映

## 設計・実装の詳細

- 全体設計: `DESIGN.md`（v1.0）、`DESIGN_V2.md`（v2.0 戦略拡張）
- Phase 1 実装報告: `IMPLEMENTATION_SUMMARY.md`
- 外部 API 仕様: `docs/API_PROTOCOL.md`
- MailMindHub 連携: `integrations/mailmindhub/`
- エージェント向けガイドライン: `AGENTS.md`
