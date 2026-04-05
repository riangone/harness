# Multi-AI Harness WebUI

複数のAI CLI（Claude / Qwen / Gemini / Codex / GitHub Copilot）を役割分担で管理・実行するWebUIです。
ハーネスエンジニアリングの原則（Generator/Evaluator分離、再発防止の仕組み化）に基づいて設計されています。

アクセス: `https://mah.0101.click`（Caddy経由）/ `http://localhost:10000`（直接）

---

## 設計概要

### アーキテクチャ

```
┌─────────────────────────────────────────────────┐
│  Browser (HTMX)                                  │
│  hx-get / hx-post / hx-delete でHTMLフラグメント │
└───────────────────┬─────────────────────────────┘
                    │ HTTPS
┌───────────────────▼─────────────────────────────┐
│  Caddy (mah.0101.click → localhost:10000)        │
└───────────────────┬─────────────────────────────┘
                    │ HTTP
┌───────────────────▼─────────────────────────────┐
│  FastAPI (port 10000)                            │
│  ├── /login     ログイン                         │
│  ├── /logout    ログアウト                       │
│  ├── /          Dashboard                        │
│  ├── /agents    エージェント管理                  │
│  ├── /projects  プロジェクト管理                  │
│  ├── /tasks     タスク管理                        │
│  ├── /runs      実行履歴・ログ                    │
│  └── /lang/{lang} 言語切り替え                   │
└───────────────────┬─────────────────────────────┘
                    │ SQLAlchemy
┌───────────────────▼─────────────────────────────┐
│  SQLite (harness.db)                             │
│  agents / projects / tasks / runs                │
└─────────────────────────────────────────────────┘
                    │ subprocess
┌───────────────────▼─────────────────────────────┐
│  AI CLI                                          │
│  claude / qwen / gemini / codex / gh-copilot     │
└─────────────────────────────────────────────────┘
```

### 技術スタック

| レイヤー | 技術 |
|---------|------|
| Frontend | HTMX 2.0.4 + 純粋CSS（フレームワークなし） |
| Backend | FastAPI + Jinja2テンプレート |
| 認証 | セッションCookie（itsdangerous署名） |
| ORM | SQLAlchemy |
| DB | SQLite (harness.db) |
| サーバー | uvicorn |
| リバースプロキシ | Caddy（自動HTTPS） |

---

## ファイル構成

```
webui/
├── app/
│   ├── main.py           # FastAPIアプリ・ルーティング・認証エンドポイント
│   ├── database.py       # SQLite接続・セッション・シードデータ
│   ├── models.py         # SQLAlchemyモデル
│   ├── templates.py      # Jinja2テンプレート設定
│   ├── auth.py           # 認証（セッションCookie・署名検証）
│   ├── i18n.py           # 多言語翻訳辞書（中日韓英）
│   ├── routers/
│   │   ├── agents.py     # エージェントCRUD
│   │   ├── projects.py   # プロジェクトCRUD
│   │   ├── tasks.py      # タスクCRUD + 実行トリガー
│   │   └── runs.py       # 実行履歴 + ログポーリング
│   ├── services/
│   │   └── executor.py   # CLI実行・パイプライン制御
│   └── templates/
│       ├── base.html     # 共通レイアウト（サイドバー・言語切替・ハンバーガー）
│       ├── login.html    # ログインページ
│       ├── index.html    # ダッシュボード
│       ├── agents.html
│       ├── projects.html
│       ├── tasks.html
│       ├── runs.html
│       └── partials/     # HTMX用HTMLフラグメント
├── static/
│   └── style.css         # レスポンシブCSS（モバイル対応）
├── harness.db            # SQLiteデータベース
├── requirements.txt
├── start.sh              # 起動スクリプト
└── harness-webui.service # systemdサービス定義
```

---

## DBスキーマ

### Agent（エージェント）

| カラム | 型 | 説明 |
|--------|-----|------|
| id | int PK | |
| name | str | 表示名 |
| cli_command | str | claude / qwen / gemini / codex / gh-copilot |
| role | enum | planner / generator / evaluator / researcher |
| priority | int | 自動選択時の優先順位（小さいほど優先、デフォルト10） |
| system_prompt | text | エージェントへの追加指示（UTF-8） |
| is_active | bool | 有効/無効 |

### Project（プロジェクト）

| カラム | 型 | 説明 |
|--------|-----|------|
| id | int PK | |
| name | str | プロジェクト名 |
| path | str | 作業ディレクトリの絶対パス |
| description | text | 説明 |

### Task（タスク）

| カラム | 型 | 説明 |
|--------|-----|------|
| id | int PK | |
| title | str | タスク名 |
| prompt | text | エージェントへの指示内容 |
| project_id | FK | 作業ディレクトリ（NULL=自動生成） |
| agent_id | FK | 手動指定エージェント（NULL=自動選択） |
| pipeline_mode | bool | True=パイプライン実行 |
| status | enum | pending / running / completed / failed |

### Run（実行記録）

| カラム | 型 | 説明 |
|--------|-----|------|
| id | int PK | |
| task_id | FK | 対象タスク |
| agent_id | FK | 実行エージェント |
| phase | str | planning / generating / evaluating |
| status | enum | running / completed / failed |
| log | text | リアルタイムログ |
| started_at | datetime | 開始時刻 |
| finished_at | datetime | 終了時刻 |

---

## パイプライン実行フロー

### シングルモード（pipeline_mode = OFF）

```
指定エージェント（または priority 最小のエージェント）が実行
    ↓
完了 / 失敗
```

### パイプラインモード（pipeline_mode = ON）

```
[Planner]  仕様策定
    ↓ 失敗 → タスクFailed
[Generator]  実装（priority昇順で自動選択、最大3回リトライ）
    ↓
[Evaluator]  品質評価
    ↓ 問題あり → Generatorに戻る（最大3回）
    ↓ 問題なし → タスクCompleted
```

**CLIコマンド実行形式**:

| CLI | 実行コマンド |
|-----|------------|
| claude / qwen / gemini / codex | `{cli} --yolo "{prompt}"` |
| gh-copilot | `gh copilot suggest -t shell "{prompt}"` |

---

## セットアップ

### 初回セットアップ

```bash
cd /home/ubuntu/ws/harness/webui
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

初回起動時にデフォルトエージェントが自動登録されます（DB が空の場合のみ）。

### 起動

```bash
# 直接起動
./start.sh

# systemdサービス
sudo systemctl start harness-webui
sudo systemctl status harness-webui
sudo systemctl stop harness-webui

# ログ確認
journalctl -u harness-webui -f
```

---

## 認証

### ログイン

`https://mah.0101.click/login`（または `http://localhost:10000/login`）にアクセスし、
ユーザー名とパスワードを入力します。

**デフォルト認証情報**: `admin` / `admin`

### 認証情報の変更

`/etc/systemd/system/harness-webui.service` に環境変数を追加：

```ini
[Service]
Environment="HARNESS_USER=yourname"
Environment="HARNESS_PASSWORD=yourpassword"
Environment="HARNESS_SECRET=your-random-secret-key"
```

変更後：

```bash
sudo systemctl daemon-reload
sudo systemctl restart harness-webui
```

### 仕組み

- ログイン成功時に `itsdangerous` で署名された `harness_session` Cookieを発行
- 全ページで Cookie を検証。未認証の場合は `/login` へ 302 リダイレクト
- `/logout` でCookieを削除

---

## 多言語対応

ナビゲーションバーの言語セレクターで切り替えられます。

| 言語 | コード |
|------|--------|
| English | `en` |
| 中文 | `zh` |
| 日本語 | `ja` |
| 한국어 | `ko` |

選択した言語は Cookie（`lang`、1年間有効）に保存されます。
翻訳辞書は `app/i18n.py` で管理。新しいキーはここに追加します。

---

## モバイル対応

- **768px以下**: サイドバーが折りたたまれ、ハンバーガーメニューで展開
- **テーブル**: 横スクロール対応
- **フォーム**: full-width レイアウト
- **統計カード**: 2列グリッドに変更

---

## デフォルトエージェント構成

初回起動時に以下のエージェントが自動登録されます：

| Name | CLI | Role | Priority |
|------|-----|------|----------|
| Claude Planner | claude | planner | 10 |
| Qwen Generator | qwen | generator | 10 |
| Claude Evaluator | claude | evaluator | 10 |
| Gemini Researcher | gemini | researcher | 10 |
| Gemini Bug Fixer | gemini | generator | 5 |
| Codex Generator | codex | generator | 15 |
| GitHub Copilot | gh-copilot | generator | 20 |

Priority が小さいほどパイプライン自動選択時に優先されます。
WebUI `/agents` の Edit フォームからいつでも変更できます。

---

## 操作ガイド

### Step 1: ログイン

`https://mah.0101.click` にアクセス → `admin` / `admin` でログイン

### Step 2: プロジェクトを登録する

`/projects` → **+ Add Project**

- **Path**: 作業ディレクトリの絶対パス（例: `/home/ubuntu/ws/myapp`）
- 存在しないパスは実行時に自動作成されます

### Step 3: タスクを作成して実行する

`/tasks` → **+ Add Task**

| フィールド | 説明 |
|-----------|------|
| Title | タスク名 |
| Prompt | エージェントへの具体的な指示 |
| Project | 作業ディレクトリ（未指定時は `/tmp/harness-{id}`） |
| Agent | 手動でエージェントを指定（未指定時は priority 最小を自動選択） |
| Pipeline Mode | ON = planner → generator → evaluator の順で自動実行 |

▶ Run ボタンで実行開始。

### Step 4: 実行ログを確認する

`/runs` でリアルタイムログをポーリング表示（2秒ごと自動更新）。
キャンセルボタンでプロセスを強制終了できます。

---

## HTMX パターン

| 操作 | パターン |
|------|---------|
| フォーム送信 | `hx-post` でテーブル行を更新 |
| 削除 | `hx-delete` で該当行を削除 |
| リスト初期ロード | `hx-get` + `hx-trigger="load"` |
| ログポーリング | `hx-trigger="every 2s"` で自動更新 |
| ページ遷移 | `hx-boost="true"` でAJAX化 |

---

## ハーネス改善ルール

エージェントがミスをするたびに `AGENTS.md` に追記し、再発を防ぎます。

```
1. /runs のログでミスを確認
2. 根本原因を分析
3. AGENTS.md に再発防止ルールを追記
4. WebUI /agents の system_prompt にも反映
```
