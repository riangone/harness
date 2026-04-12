# 統合テストシナリオ集 — 自然言語対応版

> バージョン: 2.1.0
> 更新日: 2026-04-13
> 対象: harness × MailMindHub 連携テスト（全タスクタイプ対応）

---

## テスト環境準備

```bash
# サービス起動確認
curl http://localhost:7500/api/v1/health
# → {"status":"ok","service":"harness","version":"2.0.0"}

# ルーティング動作確認（ローカル）
python3 -c "
from core.gateway.mail import MailGateway
gw = MailGateway()
rule = gw.match_routing_rule('AIについて調査して', 'レポートを作ってください')
print(rule.task_type if rule else 'no_match')
"
# → research
```

---

## テストシナリオ一覧

| # | カテゴリ | シナリオ名 | タスクタイプ | Pipeline |
|---|---|---|---|---|
| **A系** | **コード開発** | | | |
| A-1 | コード開発 | 自然言語でコード生成 | code_generation | code_generation |
| A-2 | コード開発 | 従来コマンドで生成（後方互換） | code_generation | code_generation |
| A-3 | コード開発 | 自然言語でバグ修正 | code_generation | bug_fix |
| A-4 | コード開発 | セキュリティレビュー依頼 | code_review | code_review |
| **B系** | **調査・リサーチ** | | | |
| B-1 | 調査 | 技術トレンド調査 | research | research |
| B-2 | 調査 | 競合分析レポート | research | research |
| B-3 | 調査 | 株価・市場調査 | research | research |
| B-4 | 調査 | 法律・規制調査 | research | research |
| **C系** | **文章・執筆** | | | |
| C-1 | 執筆 | ブログ記事作成 | writing | writing |
| C-2 | 執筆 | ビジネスメール作成 | writing | writing |
| C-3 | 執筆 | SNS投稿文作成 | writing | writing |
| C-4 | 執筆 | 小説・創作 | writing | writing |
| C-5 | 執筆 | 求人票・採用文書 | writing | writing |
| **D系** | **ドキュメント・資料** | | | |
| D-1 | 資料 | 営業向けPPTスライド | document | document |
| D-2 | 資料 | 技術仕様書 | document | document |
| D-3 | 資料 | 会議議事録 | document | document |
| D-4 | 資料 | ユーザーマニュアル | document | document |
| D-5 | 資料 | プロジェクト計画書 | document | document |
| **E系** | **ファイル操作** | | | |
| E-1 | ファイル | フォルダ整理 | file_ops | file_ops |
| E-2 | ファイル | 一括リネーム | file_ops | file_ops |
| **F系** | **汎用・その他** | | | |
| F-1 | 汎用 | 翻訳依頼 | general | default |
| F-2 | 汎用 | 計算・データ分析 | general | default |
| F-3 | 汎用 | アドバイス・相談 | general | default |
| F-4 | 汎用 | 不明確な指示 | general | default |
| **G系** | **システム動作確認** | | | |
| G-1 | システム | ヘルプコマンド | reply_help | — |
| G-2 | システム | Webhook コールバック疎通 | — | — |
| G-3 | システム | 並列タスク実行 | mixed | — |
| G-4 | システム | タスクキャンセル | — | — |

---

## A系: コード開発テスト

### A-1: 自然言語でコード生成

**目的**: プレフィックスなしの自然言語でコード生成タスクが起動されることを確認

**送信内容**:
```
件名: Pythonで二分探索を実装してほしい
本文:
整数リストに対する二分探索関数を作ってください。

要件：
- 対象リストは昇順にソート済みとする
- 見つかった場合はインデックス、見つからない場合は -1 を返す
- 型ヒントを含める
- 単体テストも合わせて作成
```

**API直接テスト**:
```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Pythonで二分探索を実装してほしい",
    "body": "整数リストに対する二分探索関数を作ってください。\n型ヒントを含め、単体テストも合わせて作成してください。",
    "from_addr": "dev@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
```

**期待レスポンス**:
```json
{"task_id": 1, "status": "pending", "message": "タスクが作成されました。Pipeline: code_generation"}
```

**ルーティング確認**:
```bash
python3 -c "
from core.gateway.mail import MailGateway
gw = MailGateway()
rule = gw.match_routing_rule('Pythonで二分探索を実装してほしい', '整数リストに対する二分探索関数')
print('task_type:', rule.task_type)  # → code_generation
"
```

**完了後の確認**:
```bash
curl http://localhost:7500/api/v1/tasks/1 | python3 -m json.tool
# runs[].phase に planning / generating / evaluating が含まれること
# eval_verdict: "PASS"
```

---

### A-2: 従来コマンドで生成（後方互換）

**目的**: `/generate` プレフィックスが引き続き動作することを確認

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "/generate FizzBuzz関数",
    "body": "/generate 1から100まで、3の倍数はFizz、5の倍数はBuzz、両方の倍数はFizzBuzzを出力するPython関数",
    "from_addr": "dev@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
```

**確認ポイント**: `/generate` プレフィックス付きでも同じ `code_generation` パイプラインが起動すること。

---

### A-3: 自然言語でバグ修正

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "ログイン処理でエラーが出て困っています",
    "body": "以下のコードでNullPointerExceptionが発生します。\n\ndef login(username, password):\n    user = db.find(username)\n    if user.password == password:\n        return True\n\nusernameが空の場合にクラッシュします。修正してください。",
    "from_addr": "dev@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
```

**期待**: `task_type=code_generation`（「エラー」「修正」キーワードで検出）

---

### A-4: セキュリティレビュー依頼

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "/review 認証コードのセキュリティを確認してください",
    "body": "/review 以下のコードのセキュリティ問題を指摘してください：\n\ndef authenticate(username, password):\n    sql = f\"SELECT * FROM users WHERE user='"'"'{username}'"'"' AND pass='"'"'{password}'"'"'\"\n    return db.execute(sql)",
    "from_addr": "security@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
```

---

## B系: 調査・リサーチテスト

### B-1: 技術トレンド調査

**目的**: 自然言語の調査依頼が `research` パイプラインにルーティングされることを確認

**送信内容**:
```
件名: 2026年のAI・LLM技術トレンドを調査してください
本文:
最新のAI/LLM技術動向についてまとめたレポートを作成してください。

以下の観点を含めてください：
- 主要なモデル（GPT、Claude、Gemini、Qwen）の動向
- オープンソースモデルの進化
- エンタープライズ採用の状況
- 今後12ヶ月の予測
```

**APIテスト**:
```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "2026年のAI・LLM技術トレンドを調査してください",
    "body": "最新のAI/LLM技術動向についてまとめたレポートを作成してください。主要モデルの動向、オープンソースの進化、エンタープライズ採用、今後の予測を含めてください。",
    "from_addr": "researcher@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# 期待: task_type=research, pipeline=research
```

**成果物確認**:
```bash
TASK_ID=<上記で返ったtask_id>
# 完了後
curl http://localhost:7500/api/v1/tasks/$TASK_ID | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Status:', d['status'])
print('Result preview:', (d.get('result') or '')[:300])
"
```

---

### B-2: 競合分析レポート

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "クラウドストレージサービスの競合比較レポートをまとめて",
    "body": "AWS S3、Google Cloud Storage、Azure Blob Storage、Cloudflare R2を比較した調査レポートを作成してください。料金・性能・機能・ユースケースを比較表形式で。",
    "from_addr": "pm@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「まとめて」「レポート」→ research
```

---

### B-3: 株価・市場調査（フォールバック確認）

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "最近の半導体業界の動向を教えてください",
    "body": "NVIDIAを中心とした半導体業界の最新ニュースとトレンドをまとめてください。",
    "from_addr": "analyst@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「ニュース」「トレンド」→ research
```

---

### B-4: 法律・規制調査

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "EU AI規制法（AI Act）について調査してレポートを作成してください",
    "body": "EUのAI Act（AI規制法）の概要、規制対象、ビジネスへの影響、施行スケジュールについて調べて報告書にまとめてください。",
    "from_addr": "legal@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「調査」「報告書」→ research
```

---

## C系: 文章・執筆テスト

### C-1: ブログ記事作成

**目的**: 文章執筆依頼が `writing` パイプラインにルーティングされることを確認

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "初心者向けDockerの入門ブログ記事を書いてください",
    "body": "Dockerを一度も使ったことがないエンジニア向けの入門ブログ記事を作成してください。\n\n要件：\n- 約2000文字\n- コンテナとは何かから説明\n- 基本コマンドのサンプル付き\n- 親しみやすいトーン",
    "from_addr": "writer@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「ブログ記事」「書いて」→ writing
```

---

### C-2: ビジネスメール作成

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "取引先への値上げ通知メール文を作ってください",
    "body": "来月から料金を15%値上げすることを既存取引先に通知するビジネスメールを作成してください。丁寧かつ誠実なトーンで、値上げの理由（原材料費高騰）と今後のサポート継続の意向を含めてください。",
    "from_addr": "sales@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「メール文」「作って」→ writing
```

---

### C-3: SNS投稿文作成

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "新サービスローンチのSNS投稿文を作って",
    "body": "AIを活用したタスク管理サービス『TaskMind』をリリースしました。Twitter/X向けに5パターンの告知ツイートを作成してください。ハッシュタグ #AI #タスク管理 を含め、各280文字以内で。",
    "from_addr": "marketing@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「SNS」「ツイート」→ writing
```

---

### C-4: 小説・創作

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "SF短編小説の冒頭シーンを書いてほしい",
    "body": "2089年、AIが人間の記憶を売買できる時代を舞台にしたSF短編小説の冒頭シーン（約800文字）を書いてください。主人公は記憶を売って生計を立てる30代女性。緊張感のある書き出しで。",
    "from_addr": "novelist@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「小説」「書いて」→ writing
```

---

### C-5: 求人票作成

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "シニアエンジニア採用の求人票を作成してください",
    "body": "以下の条件でシニアバックエンドエンジニアの求人票を作成してください。\n\n会社: テックスタートアップA社\n募集職種: シニアバックエンドエンジニア（Go/Python）\n給与: 700〜1200万円\n必須: 5年以上の開発経験、クラウド設計経験\n特徴: フルリモート、裁量労働制",
    "from_addr": "hr@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「書いて」「作成」→ writing（汎用執筆）
```

---

## D系: ドキュメント・資料作成テスト

### D-1: 営業向けPPTスライド

**目的**: ドキュメント作成依頼が `document` パイプラインにルーティングされることを確認

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "新SaaSサービス紹介PPTを作ってください（10枚）",
    "body": "BtoB向けAIタスク管理SaaS「TaskMind」の営業提案スライドを作成してください。\n\n構成案：\n1. 表紙\n2. 課題提起\n3. ソリューション概要\n4. 主要機能3つ\n5. 導入事例（仮）\n6. 料金プラン\n7. 競合比較\n8. 導入の流れ\n9. サポート体制\n10. お問い合わせ",
    "from_addr": "sales@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「PPT」「スライド」→ document
```

**成果物確認**（Markdown スライド形式）:
```bash
TASK_ID=<task_id>
curl http://localhost:7500/api/v1/tasks/$TASK_ID | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('result', '')[:500])
"
# → # スライド 1: TaskMind ... のMarkdown形式が返る
```

---

### D-2: 技術仕様書

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "ユーザー認証APIの技術仕様書を書いて",
    "body": "JWT認証を使ったRESTful APIの技術仕様書を作成してください。\n\nエンドポイント：\n- POST /auth/login\n- POST /auth/logout\n- POST /auth/refresh\n- GET /auth/me\n\n各エンドポイントのリクエスト・レスポンス仕様、エラーコード、シーケンス図（テキスト形式）を含めてください。",
    "from_addr": "architect@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「仕様書」「書いて」→ document
```

---

### D-3: 会議議事録

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "先ほどの会議の議事録をまとめてください",
    "body": "以下のメモから議事録を作成してください。\n\n【会議情報】\n日時: 2026-04-13 14:00〜15:30\n参加者: 田中PM、鈴木Dev、山田Design、佐藤QA\n\n【メモ】\n- リリース日は4/30で合意\n- デザインのFBは4/18まで\n- テスト開始は4/22予定\n- バグ対応は鈴木さんメイン\n- 次回MTGは4/17 15:00",
    "from_addr": "pm@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「議事録」「まとめて」→ document（「まとめて」はresearchにもマッチする可能性あり）
```

> **注意**: 「まとめて」は `research` パターンにもマッチします。件名に「議事録」を含めることで `document` にルーティングされます。優先順位は `research` > `document` なので、件名・本文の両方に `document` キーワードを含めることを推奨します。

---

### D-4: ユーザーマニュアル

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "社内向け経費精算システムのマニュアルを作成してください",
    "body": "新しく導入した経費精算システム『ExpenseEasy』の社内向けユーザーマニュアルを作成してください。\n\n含めるべき内容：\n1. ログイン方法\n2. 経費申請の流れ\n3. 領収書のアップロード方法\n4. 承認ワークフロー\n5. よくある質問",
    "from_addr": "admin@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「マニュアル」→ document
```

---

### D-5: プロジェクト計画書

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Webアプリリニューアルプロジェクトの計画書を作成してください",
    "body": "コーポレートサイトのリニューアルプロジェクト計画書を作成してください。\n\n概要: Next.js + Tailwind CSSで完全リニューアル\n期間: 2026/05/01〜2026/07/31（3ヶ月）\nチーム: PM1名、Dev2名、Design1名\n\nWBS、マイルストーン、リスク管理表を含めてください。",
    "from_addr": "pm@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「ドキュメント」「計画書」→ document
```

---

## E系: ファイル・フォルダ操作テスト

### E-1: フォルダ整理

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "/tmpのフォルダを整理してほしい",
    "body": "/tmp/uploads/ 以下にある画像ファイルを日付別（YYYY-MM-DD形式）のサブフォルダに整理してください。ファイル名から日付が判断できない場合は /tmp/uploads/misc/ に移動してください。",
    "from_addr": "ops@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「フォルダを整理」→ file_ops
```

---

### E-2: 一括リネーム

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "ファイルを一括リネームするスクリプトを作って実行して",
    "body": "/tmp/photos/ 内の .jpg ファイルを photo_001.jpg, photo_002.jpg ... の形式に一括リネームするPythonスクリプトを作成して実行してください。既存のファイルに影響が出ないようバックアップも作成してください。",
    "from_addr": "ops@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# キーワード「一括」「リネーム」→ file_ops
```

---

## F系: 汎用・その他テスト

### F-1: 翻訳依頼

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "以下の英文を自然な日本語に翻訳してください",
    "body": "Please translate the following text to natural Japanese:\n\n\"Artificial intelligence is rapidly transforming industries across the globe. From healthcare to finance, AI systems are becoming integral to decision-making processes, raising important questions about accountability, transparency, and the future of human work.\"",
    "from_addr": "translator@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# どのキーワードにもマッチしない → general (default pipeline)
```

---

### F-2: 計算・データ分析

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "売上データの簡単な分析をしてほしい",
    "body": "以下の月次売上データを分析してください：\n\n1月: 450万円\n2月: 380万円\n3月: 520万円\n4月: 610万円\n5月: 590万円\n6月: 680万円\n\n前月比成長率、累計、平均、最高月を計算し、トレンドを考察してください。",
    "from_addr": "analyst@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# → general (default pipeline)
```

---

### F-3: アドバイス・相談

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "スタートアップの資金調達戦略についてアドバイスをください",
    "body": "シードステージのBtoB SaaSスタートアップです。現在のMRRは80万円。次のステップとしてエンジェル投資家からの調達（3000万円）とVCラウンド（1億円）のどちらを優先すべきか、メリット・デメリットを整理したうえでアドバイスをください。",
    "from_addr": "founder@startup.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# → general (default pipeline)
```

---

### F-4: 意図不明な指示（フォールバック確認）

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "困っています",
    "body": "何か助けてほしいです",
    "from_addr": "user@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
# どのルールにもマッチ → general (default pipeline でエージェントが意図を解釈)
```

---

## G系: システム動作確認テスト

### G-1: ヘルプコマンド

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "/help",
    "body": "",
    "from_addr": "user@example.com",
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
```

**期待レスポンス**:
```json
{
  "task_id": null,
  "status": "unknown_command",
  "message": "無法识别的命令，已生成帮助信息",
  "help_sent": true
}
```

**確認ポイント**: MailMindHub がヘルプ内容（自然言語対応の説明付き）をユーザーにメール送信すること。

---

### G-2: Webhook コールバック疎通

```bash
# MailMindHub の受信エンドポイントへの疎通確認
curl -s -X POST http://localhost:7500/api/v1/callback/test \
  -H "X-Callback-URL: http://mailmindhub:8080/api/harness/callback"
```

**期待レスポンス**:
```json
{"status": "ok", "response_code": 200, "url": "http://mailmindhub:8080/api/harness/callback"}
```

---

### G-3: 異なるタイプの並列タスク実行

```bash
#!/bin/bash
# 5種類のタスクを同時投入して並列実行を確認

HARNESS_URL="http://localhost:7500"
CALLBACK_URL="http://mailmindhub:8080/api/harness/callback"

submit_task() {
  local subject="$1"
  local body="$2"
  local tag="$3"
  RESULT=$(curl -s -X POST "$HARNESS_URL/api/v1/tasks/from-email" \
    -H "Content-Type: application/json" \
    -d "{\"subject\":\"$subject\",\"body\":\"$body\",\"from_addr\":\"test@example.com\",\"callback_url\":\"$CALLBACK_URL\"}")
  echo "[$tag] $(echo $RESULT | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f"task_id={d.get(\"task_id\")}, status={d[\"status\"]}")')"
}

# 並列投入（各タスクは非同期実行）
submit_task "Pythonでソートを書いて" "クイックソートを実装して" "CODE" &
submit_task "AIトレンドを調査して" "2026年のAI動向をまとめて" "RESEARCH" &
submit_task "ブログ記事を書いてください" "Dockerの入門記事を作成して" "WRITING" &
submit_task "PPTスライドを作って" "新サービスの提案スライド5枚" "DOCUMENT" &
submit_task "何でも質問を答えて" "円周率を小数点以下10桁まで" "GENERAL" &
wait

echo ""
echo "=== 全タスク投入完了。ステータス確認 ==="
sleep 5
curl -s "$HARNESS_URL/api/v1/tasks?limit=10" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for t in d['tasks']:
    print(f\"  task_{t['task_id']:3d}: {t['status']:10s} | {t['title'][:50]}\")
"
```

---

### G-4: タスクキャンセル

```bash
# タスクを投入して実行中にキャンセル
TASK=$(curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "非常に複雑な調査タスク（キャンセルテスト用）",
    "body": "世界中のすべての技術について網羅的に調査してください（このタスクはキャンセルテスト用）",
    "from_addr": "test@example.com"
  }')
TASK_ID=$(echo "$TASK" | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")

echo "Task $TASK_ID 投入完了。3秒後にキャンセル..."
sleep 3

curl -s -X POST "http://localhost:7500/api/v1/tasks/$TASK_ID/cancel"
# → {"task_id": N, "status": "cancelled", "message": "タスクが取消されました"}
```

---

## 一括テストスクリプト

以下を `scripts/test-all-scenarios.sh` として保存して実行：

```bash
#!/bin/bash
# 全シナリオ一括テスト

set -e

HARNESS_URL="${HARNESS_API_URL:-http://localhost:7500}"
CALLBACK_URL="${MAILMINDHUB_CALLBACK_URL:-http://mailmindhub:8080/api/harness/callback}"
PASS=0
FAIL=0

check_route() {
  local subject="$1"
  local body="$2"
  local expected_type="$3"

  actual=$(python3 -c "
import sys; sys.path.insert(0, '.')
from core.gateway.mail import MailGateway
gw = MailGateway()
rule = gw.match_routing_rule('$subject', '$body')
print(rule.task_type if rule else 'no_match')
" 2>/dev/null)

  if [ "$actual" = "$expected_type" ]; then
    echo "  ✅ [$expected_type] $subject"
    PASS=$((PASS+1))
  else
    echo "  ❌ Expected=$expected_type Actual=$actual | $subject"
    FAIL=$((FAIL+1))
  fi
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. ルーティングルール単体テスト"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# コード系
check_route "/generate ソート関数を書いて" "" "code_generation"
check_route "/review セキュリティ確認" "" "code_review"
check_route "/fix NullPointerException" "" "bug_fix"
check_route "Pythonで二分探索を実装して" "コードを作成してほしい" "code_generation"
check_route "バグを直してほしい" "エラーが発生している" "code_generation"

# 調査系
check_route "AIトレンドを調査してください" "" "research"
check_route "競合のレポートをまとめて" "" "research"
check_route "最新ニュースを教えて" "" "research"
check_route "市場調査をお願いします" "" "research"

# 執筆系
check_route "ブログ記事を書いてください" "" "writing"
check_route "メール文を作って" "" "writing"
check_route "SNSの投稿文を作成して" "" "writing"
check_route "小説の冒頭を書いて" "" "writing"

# ドキュメント系
check_route "PPTスライドを作って" "" "document"
check_route "仕様書を書いてほしい" "" "document"
check_route "議事録を作成して" "" "document"
check_route "マニュアルを作って" "" "document"

# ファイル操作系
check_route "フォルダを整理してほしい" "" "file_ops"
check_route "ファイルを一括リネームして" "" "file_ops"

# 汎用フォールバック
check_route "翻訳してください" "英文を日本語に" "general"
check_route "教えてください" "円周率は" "general"
check_route "困っています" "" "general"

echo ""
echo "結果: ✅ $PASS件PASS / ❌ $FAIL件FAIL"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. API ヘルスチェック"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
HEALTH=$(curl -s "$HARNESS_URL/api/v1/health")
echo "$HEALTH"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. 代表タスク投入（各タイプ1件）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

for scenario in \
  "code|Pythonで二分探索を実装して|要件：型ヒント付き、単体テスト含む" \
  "research|AIトレンドを調査してレポートを作成して|2026年のLLM最新動向をまとめてください" \
  "writing|Docker入門のブログ記事を書いて|初心者向け、約1000文字、親しみやすいトーンで" \
  "document|新サービス紹介PPTを作って|SaaS製品の提案スライド5枚構成で" \
  "general|以下を翻訳してください|Hello, World! を日本語に"; do

  IFS='|' read -r tag subject body <<< "$scenario"
  RESULT=$(curl -s -X POST "$HARNESS_URL/api/v1/tasks/from-email" \
    -H "Content-Type: application/json" \
    -d "{\"subject\":\"$subject\",\"body\":\"$body\",\"from_addr\":\"test@example.com\",\"callback_url\":\"$CALLBACK_URL\"}")
  TASK_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id','N/A'))" 2>/dev/null)
  STATUS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
  echo "  [$tag] task_id=$TASK_ID status=$STATUS"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ テスト完了"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

**実行方法**:
```bash
chmod +x scripts/test-all-scenarios.sh
cd /home/ubuntu/ws/harness && ./scripts/test-all-scenarios.sh
```

---

## テスト結果の見方

### タスク詳細確認

```bash
# 特定タスクの詳細
curl http://localhost:7500/api/v1/tasks/{task_id} | python3 -m json.tool

# 確認すべきフィールド
# - status: completed / failed
# - result: 成果物の内容（非nullであること）
# - runs[].phase: planning / generating / evaluating
# - runs[].eval_verdict: PASS / FAIL
```

### ルーティング期待値まとめ

```bash
python3 -c "
from core.gateway.mail import MailGateway
gw = MailGateway()

cases = [
    ('Pythonでコードを書いて', 'code_generation'),
    ('バグを修正して', 'code_generation'),
    ('調査レポートを作って', 'research'),
    ('最新トレンドを調べて', 'research'),
    ('ブログ記事を書いて', 'writing'),
    ('手紙を書いてください', 'writing'),
    ('PPTを作って', 'document'),
    ('仕様書を書いて', 'document'),
    ('フォルダを整理して', 'file_ops'),
    ('翻訳してください', 'general'),
]
for subject, expected in cases:
    rule = gw.match_routing_rule(subject, '')
    actual = rule.task_type if rule else 'no_match'
    icon = '✅' if actual == expected else '❌'
    print(f'{icon} {expected:18s} ← {actual:18s} | {subject}')
"
```

---

## トラブルシューティング

| 症状 | 原因 | 対処法 |
|---|---|---|
| 「まとめて」が `research` になるのに `document` にしたい | `research` パターンが `document` より優先 | 件名に「議事録」「仕様書」など `document` キーワードを明示 |
| 自然言語が `general` になる | どのキーワードにもマッチしていない | 意図するキーワードを件名か本文に追加 |
| `task_type=general` なのに code が生成される | `default` パイプラインのプランナーが意図を解釈 | 期待通りの動作。意図を正確にするにはキーワードを明示 |
| `result` フィールドが null | タスクが PASS 判定を得られなかった | `runs[].eval_verdict` を確認して再試行 |
| `status=failed` | エージェント CLI が見つからない | `which qwen` / `which claude` で CLI の存在を確認 |

---

*ドキュメントバージョン: 2.1.0 | 作成日: 2026-04-13*
