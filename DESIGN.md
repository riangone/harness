# Multi-AI Harness 設計ドキュメント

最終更新: 2026-04-11

## 概要

複数のAI CLIを役割分担させるハーネス設計。
ハーネスエンジニアリングの原則（Generator/Evaluator分離、再発防止の仕組み化）に基づく。

**設計の核心原則（Claude Managed Agents から採用）:**
- **コンテキスト分離**: エージェントはそれぞれ独立したコンテキストで動作する。前のフェーズの全会話履歴は渡さない
- **アーティファクト連鎖**: フェーズ間のコンテキストはファイル（`plan.md`, `eval-report.md`）として `work_dir` に書き出し、次フェーズが明示的に読む
- **構造化評価**: Evaluator は単なる exit code ではなく `VERDICT: PASS|FAIL` + 具体的な指摘を出力する
- **フィードバックループ**: Generator の再試行時は必ず Evaluator の指摘を含めたプロンプトを渡す

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
| **planner** | Claude | 仕様策定・タスク分解・`plan.md` 出力 |
| **generator** | Qwen（優先）/ Gemini / Codex / gh-copilot | 実装・コード生成・バグ修正 |
| **evaluator** | Claude | 品質評価・構造化レポート（`eval-report.md`）出力 |
| **researcher** | Gemini | 大規模調査・Web検索 |

### 役割の詳細

**planner（Claude）**
- アーキテクチャ設計・仕様策定
- 1〜4行のプロンプトを詳細仕様に展開
- 出力: `work_dir/plan.md`（次フェーズで Generator が読む）
- AGENTS.md / CLAUDE.md の更新判断

**generator（Qwen優先）**
- `plan.md` を読んで実装する（プランナーが出力した場合）
- 定型コード生成（テスト・CRUD・型定義・ボイラープレート）
- バグ修正・リファクタリング（Gemini Bug Fixer が priority=5 で優先）
- 設定ファイル・ドキュメント生成
- 繰り返し発生する実装タスク
- 再試行時: `eval-report.md` を読んで具体的な問題を修正する

**evaluator（Claude）**
- `plan.md`（存在する場合）と生成されたコードを読んで評価
- 出力: `work_dir/eval-report.md`（構造化フォーマット）
- 仕様通りの動作確認
- セキュリティ・品質レビュー
- 具体的な修正箇所の指摘

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
[Planner]  plan.md を生成
    ↓ 失敗 → タスクFailed
[Generator]  plan.md を読んで実装（priority昇順で自動選択）
    ↓ 失敗 → retry（最大3回、plan.md継続参照）
[Evaluator]  plan.md + 実装を読んで eval-report.md を生成
    ↓ VERDICT: FAIL → eval-report.md をGeneratorに渡してretry（最大3回）
    ↓ VERDICT: PASS → タスクCompleted
```

#### コンテキスト連鎖の詳細

各フェーズは `work_dir` を共有ディレクトリとして使う。
エージェント間の「会話履歴」は渡さず、**ファイルだけが受け渡し手段**。

```
work_dir/
├── plan.md          # Planner が書く（Generator が読む）
├── eval-report.md   # Evaluator が書く（Generator retry 時に読む）
└── [実装ファイル群]  # Generator が書く（Evaluator が読む）
```

**フェーズ別プロンプト構成:**

| フェーズ | プロンプトに含まれる情報 |
|----------|------------------------|
| planning | `system_prompt` + `task.prompt` + 「plan.md に出力せよ」の指示 |
| generating | `system_prompt` + `task.prompt` + `plan.md の内容`（存在する場合） |
| generating (retry) | generating の内容 + `eval-report.md の内容`（問題の具体的内容） |
| evaluating | `system_prompt` + `task.prompt` + `plan.md の内容` + 「eval-report.md に構造化出力せよ」の指示 |

**エージェント自動選択ルール**: 同ロール内で `priority` 値が小さいエージェントを優先。
WebUIの `/agents` で各エージェントのpriorityを設定することで制御する。

**CLIコマンド実行形式**:

| CLI | 実行コマンド |
|-----|------------|
| claude | `claude -p "{prompt}" --dangerously-skip-permissions` |
| qwen | `qwen -y "{prompt}"` |
| gemini | `gemini -p "{prompt}"` |
| codex | `codex exec "{prompt}"` |
| gh-copilot | `gh copilot suggest -t shell "{prompt}"` |

---

## 評価プロトコル（Evaluator 出力フォーマット）

Evaluator は `work_dir/eval-report.md` に以下の形式で出力する。
ハーネスはこのファイルを読んで `VERDICT` 行を解析し、PASS/FAIL を判定する。

```markdown
# 評価レポート

VERDICT: PASS

## 確認事項
- [x] 仕様通りに動作している
- [x] エッジケースが処理されている
- [x] セキュリティ上の問題なし
```

失敗の場合:

```markdown
# 評価レポート

VERDICT: FAIL

## 問題点
- ISSUE[1]: src/auth.py:42 — パスワードがプレーンテキストで保存されている。bcrypt でハッシュ化すること
- ISSUE[2]: src/api.py:87 — SQL インジェクション脆弱性。parameterized query を使うこと
- ISSUE[3]: テスト未実装 — test_auth.py が存在しない

## 修正優先度
HIGH: ISSUE[1], ISSUE[2]
MEDIUM: ISSUE[3]
```

ハーネスの評価判定ロジック:
1. `eval-report.md` が存在し `VERDICT: PASS` を含む → 成功
2. `eval-report.md` が存在し `VERDICT: FAIL` を含む → 問題あり、`ISSUE[N]` を抽出して Generator に渡す
3. `eval-report.md` が存在しない、または evaluator の exit code が非ゼロ → 評価失敗

---

## エラー分類と再試行戦略

### エラー種別

| 種別 | 例 | 対応 |
|------|-----|------|
| 一時的エラー | 429 Rate Limit、ネットワークタイムアウト | exponential backoff で再試行 |
| 実装品質エラー | VERDICT: FAIL | eval-report.md を渡して Generator retry |
| 設定エラー | CLI が見つからない | 即失敗、次の priority エージェントへ fallback |
| 致命的エラー | 認証失敗（401/403） | 即失敗、タスク Failed |

### パイプライン再試行戦略

```
Generator retry の際:
  attempt 1: Generator (priority 最小) + eval-report.md の問題点
  attempt 2: Generator (priority 2番目、あれば) + eval-report.md の問題点
  attempt 3: Generator (priority 3番目、あれば) + eval-report.md の問題点
  → すべて失敗 → タスク Failed
```

同じエージェントに同じ問題を何度も渡すのは非効率のため、
retry ごとに次の priority のエージェントへ fallback する（available な場合）。

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
| created_at | datetime | |

### runs

| カラム | 型 | 説明 |
|--------|-----|------|
| id | int PK | |
| task_id | FK | 対象タスク |
| agent_id | FK | 実行エージェント |
| phase | str | planning / generating / evaluating |
| attempt | int | 同フェーズ内の試行番号（1始まり） |
| status | enum | running / completed / failed |
| eval_verdict | str | PASS / FAIL / null（evaluatingフェーズのみ使用） |
| log | text | リアルタイム実行ログ |
| started_at | datetime | |
| finished_at | datetime | |

> `attempt` と `eval_verdict` は既存スキーマへの追加カラム。

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
6. /runs でリアルタイムログを確認（SSEストリーミング + Markdownレンダリング）
7. ミスがあれば AGENTS.md と system_prompt を更新
```

---

## WebUIログ表示設計（SSE + Markdownレンダリング）

### 概要

`/runs` のログ表示は **Server-Sent Events (SSE)** によるリアルタイムストリーミングと、
**marked.js** によるクライアントサイド Markdown レンダリングを採用する。

### アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│  Browser                                                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  run_log_single.html                                  │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  marked.js (クライアントサイドMDレンダリング)    │  │  │
│  │  │  ↓                                              │  │  │
│  │  │  .log-md-content (HTMLレンダリング済みログ)      │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  EventSource ────────────────┐                              │
│  (SSE接続)                   │                              │
│  ↓                           │  フォールバック              │
│  onmessage → renderMarkdown  │  /runs/{id}/log-raw          │
│                              │  (2秒ポーリング)             │
└──────────────────────────────┼──────────────────────────────┘
                               │
                    ┌──────────┼──────────┐
                    │          │          │
                    ↓          ↓          ↓
┌───────────────────────────────────────────────────┐
│  FastAPI Backend                                  │
│                                                   │
│  GET /runs/{id}/log-stream  (SSEエンドポイント)   │
│    → 1秒ごとにDBをポーリング                       │
│    → ログに更新があれば data: {json} で送信        │
│    → タスク完了で接続クローズ                      │
│                                                   │
│  GET /runs/{id}/log-raw  (フォールバック用)        │
│    → 生ログテキストを即座に返す                    │
│    → SSE未対応/切断時に使用                        │
└───────────────────────────────────────────────────┘
```

### SSEエンドポイント仕様

| 項目 | 値 |
|------|-----|
| URL | `GET /runs/{run_id}/log-stream` |
| メディアタイプ | `text/event-stream` |
| 認証 | セッションCookie必須 |
| ポーリング間隔 | 1秒 |
| データ形式 | `data: "{JSONエスケープ済みログ全文}"\n\n` |
| 終了条件 | タスク状態が `running` 以外、またはクライアント切断 |
| ヘッダー | `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no` |

### フォールバック仕様

SSEが利用できない場合（ブラウザ未対応、プロキシ経由切断等）、自動的に `/runs/{id}/log-raw` への
2秒周期HTTPポーリングに切り替える。タスク完了時にポーリングを停止する。

### Markdownレンダリング仕様

- **ライブラリ**: marked.js (CDN: `cdn.jsdelivr.net/npm/marked/marked.min.js`)
- **設定**: `breaks: true`, `gfm: true` (GitHub Flavored Markdown)
- **レンダリング対象**: `.log-md-content` 要素
- **更新方式**: 毎回全文再レンダリング（ログ追記時）
- **スクロール**: 更新後に自動スクロール（`scrollBottom()`）

### 対応Markdown要素

| 要素 | スタイル |
|------|----------|
| 見出し (h1-h4) | 白系、下部ボーダー付き |
| コード (inline) | 暗色背景、オレンジ文字 |
| コードブロック | 暗色背景、ボーダー、横スクロール |
| リスト (ul/ol) | 左パディング、白系文字 |
| 引用 (blockquote) | 左ボーダー、グレー文字 |
| テーブル | ボーダー付き、ヘッダー暗色背景 |
| 水平線 | グレーボーダー |
| リンク | ブルー、ホバーで下線 |

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

## executor.py 改修仕様

### 現状の問題点

| # | 問題 | 影響 |
|---|------|------|
| 1 | Planning 出力が Generator に渡らない | plan.md は書かれているが Generator は無視する |
| 2 | Evaluator の指摘が Generator retry に渡らない | 再試行しても改善されない |
| 3 | 評価判定が exit code 依存 | exit 0 でも問題があることがある |
| 4 | retry で同じエージェントが繰り返し呼ばれる | 同じエラーが続く |

### 改修後の `_execute_pipeline` ロジック

```python
def _execute_pipeline(db, task, work_dir):
    plan_file = os.path.join(work_dir, "plan.md")
    eval_file = os.path.join(work_dir, "eval-report.md")

    # Phase 1: Planning
    planner = _get_agents_by_role(db, "planner")
    planning_prompt = f"""{planner.system_prompt or ''}

タスク: {task.prompt}

作業ディレクトリ {work_dir}/plan.md に詳細な実装計画を出力してください。
"""
    run = _create_run(db, task, planner, "planning", attempt=1)
    success = _run_single_command(db, run, _build_command(planner.cli_command, planning_prompt), work_dir, task)
    _finish_run(db, run, success)
    if not success:
        _fail_task(db, task); return

    # Phase 2: Generation + Evaluation loop (最大3回)
    generators = _get_agents_by_role_all(db, "generator")  # priority順リスト
    for attempt in range(1, 4):
        generator = generators[min(attempt - 1, len(generators) - 1)]

        # plan.md の内容をプロンプトに組み込む
        plan_content = _read_file(plan_file)
        eval_content = _read_file(eval_file) if attempt > 1 else ""

        gen_prompt = _build_gen_prompt(generator, task, plan_content, eval_content, attempt)
        run = _create_run(db, task, generator, "generating", attempt=attempt)
        success = _run_single_command(db, run, _build_command(generator.cli_command, gen_prompt), work_dir, task)
        _finish_run(db, run, success)
        if not success:
            if attempt == 3: _fail_task(db, task); return
            continue

        # Phase 3: Evaluation
        evaluator = _get_agents_by_role(db, "evaluator")
        if not evaluator:
            _complete_task(db, task); return

        plan_content = _read_file(plan_file)
        eval_prompt = _build_eval_prompt(evaluator, task, plan_content)
        run = _create_run(db, task, evaluator, "evaluating", attempt=attempt)
        success = _run_single_command(db, run, _build_command(evaluator.cli_command, eval_prompt), work_dir, task)
        _finish_run(db, run, success)

        verdict = _parse_verdict(eval_file)
        run.eval_verdict = verdict
        db.commit()

        if verdict == "PASS":
            _complete_task(db, task); return
        if attempt == 3:
            _fail_task(db, task); return
        # else: FAIL → 次のループで eval_content を Generator に渡す

    _fail_task(db, task)
```

### 新規ヘルパー関数

```python
def _get_agents_by_role_all(db, role) -> list[Agent]:
    """指定ロールの有効エージェントを priority 昇順で全件返す"""

def _read_file(path: str) -> str:
    """ファイルを読んで文字列で返す。存在しない場合は空文字"""

def _parse_verdict(eval_file: str) -> str:
    """eval-report.md を読んで PASS / FAIL / UNKNOWN を返す"""

def _build_gen_prompt(agent, task, plan_content, eval_content, attempt) -> str:
    """Generator 用プロンプトを構築（retry 時は eval-report.md の問題点を含める）"""

def _build_eval_prompt(agent, task, plan_content) -> str:
    """Evaluator 用プロンプトを構築（eval-report.md を出力するよう指示）"""

def _finish_run(db, run, success):
    """Run を completed / failed で閉じる"""

def _fail_task(db, task):
    """Task を failed に更新"""

def _complete_task(db, task):
    """Task を completed に更新"""
```

### DBマイグレーション

`runs` テーブルに以下のカラムを追加:
```sql
ALTER TABLE runs ADD COLUMN attempt INTEGER DEFAULT 1;
ALTER TABLE runs ADD COLUMN eval_verdict TEXT;
```

---

## 今後の拡張

- [x] **スプリント契約**: タスク作成時に `success_criteria` フィールドを設け、Evaluator が契約ベースで判定
- [x] **タスク依存関係**: `depends_on` FK で前タスクの完了を待つ連鎖実行
- [x] **並列実行**: 独立したタスクを同時実行するスレッドプール管理
- [x] **エージェントヘルスチェック**: 実行前に CLI の存在確認、不在なら次 priority へ即 fallback
- [x] **実行統計・コスト追跡**: エージェントごとの `total_runs`, `total_passes`, `avg_duration_ms`, `estimated_cost` を自動集計
- [x] **タスクのスケジュール実行**: cron 式による定期実行（`schedules` テーブル + バックグラウンドスレッド）
- [x] **ユーザー管理（複数ユーザー対応）**: `users` テーブル + RBAC（admin/editor/viewer）
- [ ] **Playwright MCP による自動UI評価**（Evaluatorエージェント）
- [ ] **トレース分析による自動AGENTS.md更新**

---

## 改修履歴

| 日付 | 内容 |
|------|------|
| 2026-04-11 | Pipeline実行ロジック改修（コンテキスト分離・フィードバックループ・agent fallback） |
| 2026-04-11 | DBスキーマ拡張（`runs.attempt`, `runs.eval_verdict`） |
| 2026-04-11 | WebUIログ表示改善（SSEストリーミング + marked.js Markdownレンダリング） |
| 2026-04-11 | RunsテーブルUI表示（Attempt/Verdictカラム追加） |
| 2026-04-12 | スプリント契約（`tasks.success_criteria`）+ Evaluator 契約ベース判定 |
| 2026-04-12 | タスク依存関係（`tasks.depends_on_id`）+ 連鎖実行 |
| 2026-04-12 | 並列実行（`tasks.parallel_group` + ThreadPoolExecutor） |
| 2026-04-12 | エージェントヘルスチェック（`shutil.which` + 自動 fallback） |
| 2026-04-12 | 実行統計・コスト追跡（`agents.total_runs/passes/avg_duration_ms/estimated_cost`） |
| 2026-04-12 | スケジュール実行（`schedules` テーブル + cron + バックグラウンドスレッド） |
| 2026-04-12 | 複数ユーザー管理（`users` テーブル + RBAC: admin/editor/viewer） |

最終更新: 2026-04-11
