# Multi-AI Harness 設計ドキュメント

最終更新: 2026-04-05

## 概要

複数のAI CLIを役割分担させるハーネス設計。
ハーネスエンジニアリングの原則（Generator/Evaluator分離、再発防止の仕組み化）に基づく。

管理・実行はWebUI（FastAPI + HTMX、`https://mah.0101.click`）から行う。
エージェントの役割・優先順位・指示・認証設定はすべてWebUIまたは環境変数から動的に設定可能。

---

## 利用可能なCLI

| CLI | パス | デフォルト役割 |
|-----|------|----------------|
| `claude` | `/home/ubuntu/.local/bin/claude` | planner / evaluator |
| `qwen` | `~/.nvm/versions/node/v24.13.0/bin/qwen` | **generator（大量生成・優先）** |
| `gemini` | `~/.nvm/versions/node/v24.13.0/bin/gemini` | researcher / generator（バグ修正） |
| `codex` | `~/.nvm/versions/node/v24.13.0/bin/codex` | generator（補助） |
| `gh-copilot` | `gh copilot suggest` | generator（補助） |

> 役割・優先順位はWebUI `/agents` からいつでも変更可能。

---

## 役割定義

| Role | 担当 | 説明 |
|------|------|------|
| **planner** | Claude | 仕様策定・タスク分解 |
| **generator** | Qwen（優先）/ Gemini / Codex / gh-copilot | 実装・コード生成・バグ修正 |
| **evaluator** | Claude | 品質評価・レビュー |
| **researcher** | Gemini | 大規模調査・Web検索 |

### 役割の詳細

**planner（Claude）**
- アーキテクチャ設計・仕様策定
- 1〜4行のプロンプトを詳細仕様に展開
- AGENTS.md / CLAUDE.md の更新判断

**generator（Qwen優先）**
- 定型コード生成（テスト・CRUD・型定義・ボイラープレート）
- バグ修正・リファクタリング（Gemini Bug Fixer が priority=5 で優先）
- 設定ファイル・ドキュメント生成
- 繰り返し発生する実装タスク

**evaluator（Claude）**
- 仕様通りの動作確認
- セキュリティ・品質レビュー
- 具体的な修正箇所の指摘
- パフォーマンス最適化の判断

**researcher（Gemini）**
- コードベース全体の把握（100万tokenコンテキスト活用）
- Web上の最新情報収集
- 複数の大きなファイルにまたがる調査

---

## パイプライン実行フロー

### シングルモード（pipeline_mode = OFF）

```
タスク作成
    ↓
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

**エージェント自動選択ルール**: 同ロール内で `priority` 値が小さいエージェントを優先。
WebUIの `/agents` で各エージェントのpriorityを設定することで制御する。

**CLIコマンド実行形式**:

| CLI | 実行コマンド |
|-----|------------|
| claude / qwen / gemini / codex | `{cli} --yolo "{prompt}"` |
| gh-copilot | `gh copilot suggest -t shell "{prompt}"` |

---

## デフォルトエージェント構成

初回起動時（DB空の場合）に自動登録：

| Priority | Name | CLI | Role | 用途 |
|----------|------|-----|------|------|
| 5 | Gemini Bug Fixer | gemini | generator | バグ修正専任 |
| 10 | Claude Planner | claude | planner | 仕様策定 |
| 10 | Qwen Generator | qwen | generator | 通常の大量生成 |
| 10 | Claude Evaluator | claude | evaluator | 品質評価 |
| 10 | Gemini Researcher | gemini | researcher | 調査 |
| 15 | Codex Generator | codex | generator | 補助実装 |
| 20 | GitHub Copilot | gh-copilot | generator | コード提案 |

> priorityはWebUI `/agents` のEditフォームからいつでも変更可能。

---

## システム全体構成

```
harness/
├── DESIGN.md              # 本ドキュメント
├── AGENTS.md              # エージェント向け制約・ガイドライン
├── CLAUDE.md              # Claude向け行動指針
├── scripts/               # CLIハーネス（レガシー・手動実行用）
│   ├── run.sh
│   ├── qwen-task.sh
│   └── evaluate.sh
├── tasks/                 # タスクファイル管理（CLIモード用）
│   ├── backlog/
│   ├── in-progress/
│   └── done/
├── todo-app/              # サンプルアプリ（Qwen生成）
│   └── index.html
└── webui/                 # WebUI本体
    ├── app/
    │   ├── main.py        # FastAPIアプリ・認証エンドポイント・言語切替
    │   ├── database.py    # SQLite接続・シードデータ
    │   ├── models.py      # DBモデル
    │   ├── templates.py   # Jinja2設定
    │   ├── auth.py        # セッション認証（itsdangerous）
    │   ├── i18n.py        # 多言語翻訳辞書（中日韓英）
    │   ├── routers/       # APIルーター（全て認証・言語対応）
    │   │   ├── agents.py
    │   │   ├── projects.py
    │   │   ├── tasks.py
    │   │   └── runs.py
    │   ├── services/
    │   │   └── executor.py  # CLI実行・パイプライン制御
    │   └── templates/       # HTMX用HTMLテンプレート
    │       ├── login.html   # ログインページ
    │       ├── base.html    # 共通レイアウト（言語切替・ハンバーガー）
    │       └── partials/    # HTMXフラグメント
    ├── static/style.css     # レスポンシブCSS（モバイル対応）
    ├── harness.db           # SQLiteデータベース
    ├── requirements.txt
    ├── start.sh             # 起動スクリプト
    ├── harness-webui.service # systemdサービス定義
    └── README.md            # 使用・操作ドキュメント
```

---

## DBスキーマ

### agents

| カラム | 型 | 説明 |
|--------|-----|------|
| id | int PK | |
| name | str | 表示名 |
| cli_command | str | claude / qwen / gemini / codex / gh-copilot |
| role | enum | planner / generator / evaluator / researcher |
| priority | int | 自動選択時の優先順位（小さいほど優先、デフォルト10） |
| system_prompt | text | エージェントへの追加指示（UTF-8） |
| is_active | bool | 有効/無効 |

### projects

| カラム | 型 | 説明 |
|--------|-----|------|
| id | int PK | |
| name | str | プロジェクト名 |
| path | str | 作業ディレクトリの絶対パス |
| description | text | 説明 |

### tasks

| カラム | 型 | 説明 |
|--------|-----|------|
| id | int PK | |
| title | str | タスク名 |
| prompt | text | エージェントへの指示内容 |
| project_id | FK | 作業ディレクトリ（NULL=自動生成） |
| agent_id | FK | 手動指定エージェント（NULL=自動選択） |
| pipeline_mode | bool | True=パイプライン実行 |
| status | enum | pending / running / completed / failed |

### runs

| カラム | 型 | 説明 |
|--------|-----|------|
| id | int PK | |
| task_id | FK | 対象タスク |
| agent_id | FK | 実行エージェント |
| phase | str | planning / generating / evaluating |
| status | enum | running / completed / failed |
| log | text | リアルタイム実行ログ |
| started_at | datetime | |
| finished_at | datetime | |

---

## 認証設計

- **方式**: セッションCookie（`itsdangerous` で署名）
- **Cookie名**: `harness_session`
- **未認証時**: 全ページで `/login` へ 302 リダイレクト
- **認証情報**: 環境変数で設定

| 環境変数 | デフォルト | 説明 |
|---------|-----------|------|
| `HARNESS_USER` | `admin` | ログインユーザー名 |
| `HARNESS_PASSWORD` | `admin` | ログインパスワード |
| `HARNESS_SECRET` | `harness-secret-key-change-me` | Cookie署名キー（本番では必ず変更） |

---

## 多言語対応

- **対応言語**: 英語（en）/ 中文（zh）/ 日本語（ja）/ 한국어（ko）
- **切り替え**: ナビゲーションバーのセレクターから即時切替
- **保存**: `lang` Cookie（1年間有効）
- **翻訳辞書**: `app/i18n.py` で一元管理
- **テンプレート**: `{{ t('key') }}` 関数で参照

---

## モバイル対応

- **768px以下**: サイドバーを折りたたみ、ハンバーガーボタンで展開
- **テーブル**: `.table-wrapper` で横スクロール対応
- **フォーム**: `flex-direction: column` で縦積みレイアウト
- **統計カード**: 2列グリッドに切り替え

---

## コスト戦略

| フェーズ | 担当 | 理由 |
|---------|------|------|
| 仕様策定 | Claude | 高品質な推論が必要 |
| バグ修正 | Gemini（priority=5） | 根本原因分析に強い |
| 大量実装 | **Qwen（priority=10）** | コスト削減 |
| 品質評価 | Claude | 品質の番人 |
| 大規模調査 | Gemini | 100万tokenコンテキスト |
| 補助生成 | Codex / gh-copilot | 必要に応じて |

**原則**: Claudeの呼び出し回数を最小化し、判断・評価にのみ集中させる。
実装・生成はpriority設定でQwen/Gemini/Codexに振り分ける。

---

## ハーネス改善ルール（Mitchell Hashimoto原則）

> エージェントがミスをするたびに、そのミスが二度と起きないよう仕組みを構築する

### ミス記録フロー

1. `/runs` のログでエージェントのミスを確認
2. Claude が根本原因を分析
3. `AGENTS.md` に再発防止ルールを追記
4. WebUI `/agents` の `system_prompt` にも反映
5. 次回から同じミスが構造的に起きない状態にする

---

## タスク振り分けルール

### generator に投げるべきタスク（Qwen / Gemini / Codex / gh-copilot）
- テストコードの生成（ユニット・統合）
- CRUD / REST APIエンドポイントの実装
- 型定義・インターフェース生成
- リファクタリング（機械的な変換）
- **バグ修正**（Gemini Bug Fixer が priority=5 で自動優先）
- 設定ファイル生成（CI/CD、Dockerfile等）
- 繰り返しパターンのコード生成

### planner / evaluator に残すべきタスク（Claude）
- 設計判断が必要な仕様策定
- セキュリティレビュー
- パフォーマンス最適化の判断
- エラーパターンの分析・AGENTS.md更新
- 複雑な要件の分解

### researcher に投げるべきタスク（Gemini）
- リポジトリ全体の把握・依存関係マップ
- 複数の大きなファイルにまたがる調査
- Web上の最新情報収集

---

## WebUI操作フロー

```
1. https://mah.0101.click にアクセス → admin/admin でログイン
2. /agents  でエージェントを確認・調整（priority / system_prompt）
3. /projects でプロジェクト（作業パス）を登録
4. /tasks でタスクを作成
       - 手動でエージェントを指定、またはpipeline_modeでAI自動選択
5. Run ボタンで実行開始
6. /runs でリアルタイムログを確認（2秒ポーリング）
7. ミスがあれば AGENTS.md と system_prompt を更新
```

---

## 起動・運用

```bash
# サービス起動
sudo systemctl start harness-webui

# 状態確認
sudo systemctl status harness-webui

# ログ確認
journalctl -u harness-webui -f

# 認証情報変更後の再起動
sudo systemctl daemon-reload && sudo systemctl restart harness-webui
```

アクセス:
- 外部: `https://mah.0101.click`
- 内部: `http://localhost:10000`

---

## 今後の拡張

- [ ] Playwright MCP による自動UI評価（Evaluatorエージェント）
- [ ] スプリント契約システム（実装前に成功基準を合意）
- [ ] トレース分析による自動AGENTS.md更新
- [ ] エージェントごとの実行統計・コスト追跡
- [ ] ユーザー管理（複数ユーザー対応）
- [ ] タスクのスケジュール実行
