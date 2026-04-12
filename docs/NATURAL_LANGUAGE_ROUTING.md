# 自然言語ルーティング — 設計変更ドキュメント

> バージョン: 2.1.0
> 更新日: 2026-04-13
> 対象コミット: `516ac3f`

---

## 概要

本ドキュメントは、harness v2.1.0 で実施した**自然言語ルーティング対応**と**コード開発以外のタスク対応**の変更内容を説明します。

ユーザーはメール（またはAPI）で自然言語のまま指示できるようになりました。`/generate` などのコマンドプレフィックスは不要です。

---

## 変更の背景

### 変更前の問題点

```
ユーザー: 「AIの最新トレンドを調査してレポートを作ってください」
         ↓
harness: 「No routing rule matched」 → ヘルプメール返信
```

ユーザーが `/generate`、`/review`、`/fix` 以外の指示を送ると、harness はルールにマッチせず即座にヘルプを返していました。コード開発以外のタスク（調査、文章作成、資料作成など）は一切受け付けられませんでした。

### 変更後の動作

```
ユーザー: 「AIの最新トレンドを調査してレポートを作ってください」
         ↓
harness: キーワード「調査」「レポート」を検出 → research パイプライン起動
         ↓
         1. Planner: 調査計画を策定
         2. Generator: 調査実行・report.md 生成
         3. Evaluator: 網羅性・正確性を評価
         ↓
         Webhook → MailMindHub → ユーザーにレポートをメール返信
```

---

## 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---|---|---|
| `config/gateway.yaml` | 更新 | 自然言語ルール 5 件 + 汎用フォールバック追加 |
| `core/gateway/mail.py` | 更新 | `task_type` の metadata 伝播、ヘルプメール全面改訂 |
| `webui/app/routers/external_api.py` | 更新 | `task_type` と `input` を `task_meta` に保存 |
| `webui/app/services/executor.py` | 更新 | タスクタイプ別プロンプト、`task.result` 自動収集 |
| `templates/research.yaml` | 新規 | 調査・リサーチ Pipeline |
| `templates/writing.yaml` | 新規 | 文章執筆 Pipeline |
| `templates/document.yaml` | 新規 | ドキュメント・資料作成 Pipeline |
| `templates/file_ops.yaml` | 新規 | ファイル・フォルダ操作 Pipeline |
| `templates/default.yaml` | 更新 | 汎用フォールバック Pipeline に改訂 |

---

## ルーティングアーキテクチャ

### ルール優先順位

```
受信メール（件名 + 本文）
    │
    ├─① 明示コマンド（後方互換）
    │    /review, /generate, /fix, /help
    │
    ├─② 自然言語: コード系
    │    「コードを書いて」「実装して」「バグを直して」
    │    「関数」「クラス」「API」「エラー」「修正」
    │
    ├─③ 自然言語: 調査・リサーチ
    │    「調査して」「調べて」「レポートを作って」
    │    「まとめて」「情報収集」「トレンド」「ニュース」
    │
    ├─④ 自然言語: 文章・執筆
    │    「書いて」「ブログ記事」「小説」「手紙」
    │    「メール文」「SNS」「キャッチコピー」
    │
    ├─⑤ 自然言語: ドキュメント・資料
    │    「PPT」「スライド」「プレゼン」「PDF」
    │    「仕様書」「議事録」「マニュアル」
    │
    ├─⑥ 自然言語: ファイル・フォルダ操作
    │    「フォルダを整理」「一括リネーム」「ファイル整理」
    │
    └─⑦ 汎用フォールバック（.+）
         上記いずれにもマッチしない場合
         → default パイプライン（汎用実行）
```

### マッチングロジック

`core/gateway/mail.py:match_routing_rule()` が件名と本文を結合した文字列に対して `re.search()` を適用します。

```python
content = f"{subject}\n{body}"
for rule in self.rules:
    if re.search(rule.pattern, content, re.IGNORECASE | re.MULTILINE):
        return rule
```

- `re.IGNORECASE`: 大文字・小文字を区別しない
- `re.MULTILINE`: `^` が各行の先頭にマッチ（行頭コマンドの後方互換に必要）
- ルールは **先頭から順番にチェック**。最初にマッチしたルールが採用される

---

## タスクタイプ対応表

| タスクタイプ | パイプライン | 検出キーワード（例） | 成果物ファイル |
|---|---|---|---|
| `code_generation` | `code_generation` | コード、関数、実装、バグ | *.py / *.js など |
| `code_review` | `code_review` | レビュー、審査、セキュリティ確認 | review.md |
| `bug_fix` | `bug_fix` | バグ、エラー、直して（/fix） | 修正コード |
| `research` | `research` | 調査、調べ、レポート、まとめて | report.md |
| `writing` | `writing` | 書いて、文章、ブログ、小説、手紙 | output.md |
| `document` | `document` | PPT、スライド、仕様書、議事録 | document.md |
| `file_ops` | `file_ops` | フォルダ整理、一括リネーム | ログのみ |
| `general` | `default` | その他すべて（フォールバック） | output.md |

---

## タスクタイプ別パイプライン詳細

### research パイプライン

```
Planner（Claude）
  └─ 調査計画 → plan.md
      ↓
Generator（Qwen / Gemini）
  └─ 調査実行 → report.md
      ↓
Evaluator（Claude）
  └─ 評価基準:
     ・調査内容が網羅的か
     ・情報源が明示されているか
     ・結論・提言が明確か
     ・読みやすく構造化されているか
```

**プランナーへの指示例**:
> 調査テーマを分析し、調査スコープ・調査項目リスト・情報収集アプローチ・最終レポート構成案を plan.md に出力してください。

**ジェネレーターへの指示例**:
> 調査計画に従い、エグゼクティブサマリー・詳細調査結果・考察・結論・提言を含む report.md を出力してください。

---

### writing パイプライン

```
Planner（Claude）
  └─ 執筆計画（目的・ターゲット・構成・文体） → plan.md
      ↓
Generator（Claude 優先 / Qwen）
  └─ 文章生成 → output.md
      ↓
Evaluator（Claude）
  └─ 評価基準:
     ・依頼内容に沿った内容か
     ・文章の流れが自然か
     ・誤字・脱字がないか
     ・目的に合ったトーンか
```

---

### document パイプライン

```
Planner（Claude）
  └─ 資料構成計画（目的・対象・構成・フォーマット） → plan.md
      ↓
Generator（Qwen / Claude）
  └─ Markdown 形式で出力 → document.md
     ・PPT/スライド: --- 区切りのスライド形式
     ・仕様書: 標準 Markdown
     ・議事録: 日時・参加者・議題・決定事項・AI形式
      ↓
Evaluator（Claude）
  └─ 構成・内容・フォーマットを評価
```

**スライド出力形式**:
```markdown
# スライド 1: タイトル
## サブタイトル
- ポイント1
- ポイント2

---

# スライド 2: 〇〇
...
```

---

### default（汎用）パイプライン

どのキーワードにもマッチしなかった場合のフォールバック。プランナーがまず指示の意図を分析し、最適な実行計画を立ててから実行します。

```
Planner: 「指示の意図を把握し、成果物と手順を明確化」
Generator: 「計画に従って実行、output.md に出力」
Evaluator: 「タスク要求を満たしているか、成果物の品質確認」
```

---

## executor.py の変更詳細

### 追加された関数

#### `_get_task_type(task: Task) -> str`

```python
def _get_task_type(task: Task) -> str:
    """task_meta から task_type を読み取る"""
    if not task.task_meta:
        return 'general'
    try:
        meta = json.loads(task.task_meta)
        return meta.get('task_type', 'general')
    except Exception:
        return 'general'
```

#### `_collect_result(work_dir, task_type, run_log) -> str`

タスク完了後、タスクタイプに応じた成果物ファイルを自動収集して `task.result` に設定します。

```python
output_files = {
    'research':  ['report.md', 'output.md', 'result.md'],
    'writing':   ['output.md', 'draft.md', 'article.md', 'story.md'],
    'document':  ['document.md', 'slides.md', 'output.md'],
    'file_ops':  [],  # ログのみ
    'general':   ['output.md', 'result.md'],
}
```

ファイルが存在しない場合は、run ログの末尾 2000 文字を使用します。

### プランナープロンプトの変更

**変更前（全タスク共通）**:
> 「作業ディレクトリ {plan_file} に詳細な実装計画を出力してください。」

**変更後（タスクタイプ別）**:

| タスクタイプ | プランナーへの指示 |
|---|---|
| `code_generation` | コード実装計画（言語・設計方針・テスト計画） |
| `research` | 調査計画（調査項目・アプローチ・レポート形式）|
| `writing` | 執筆計画（構成・章立て・文体・文字数） |
| `document` | 資料構成計画（目的・セクション・フォーマット） |
| `file_ops` | ファイル操作計画（操作対象・手順・安全確認） |
| `general` | 汎用実行計画（手順・成果物・検証方法） |

### エバリュエータープロンプトの変更

**変更前**: 常にコード品質（バグ・セキュリティ・エッジケース）を評価

**変更後**: タスクタイプ別の評価チェックリストを使用

```
research  → 網羅性・正確性・情報源・構造化
writing   → 内容適合性・読みやすさ・誤字・トーン
document  → 構成論理性・内容正確性・フォーマット
file_ops  → 操作完了・データ損失なし・確認可能
general   → 要求達成・成果物明確・品質十分
```

---

## task.result の挙動変化

### 変更前

`_complete_task()` は `task.result` を設定しませんでした。Webhook コールバックの `result` フィールドは常に `null` でした。

### 変更後

```python
def _complete_task(db, task, result=None):
    task.status = TaskStatus.completed
    task.updated_at = datetime.utcnow()
    if result:
        task.result = result  # ← 成果物ファイルの内容
    db.commit()
```

`_execute_pipeline()` の PASS 時に `_collect_result()` が呼ばれ、成果物ファイルの内容が `task.result` にセットされます。これにより Webhook コールバックの `result` フィールドに実際のコンテンツが含まれるようになります。

---

## MailMindHub 側の対応推奨

### レスポンスメール生成

`task.result` に成果物が入るようになったため、MailMindHub 側でコールバックペイロードの `result` をメール本文に使用できます。

```json
// Webhook コールバックペイロード例（research タスク）
{
  "task_id": 42,
  "status": "completed",
  "title": "[email] AIの最新トレンドを調査してレポートを作ってください",
  "result": "# AI最新トレンド調査レポート\n\n## エグゼクティブサマリー\n...",
  "from_addr": "user@example.com",
  "email_content": {
    "subject": "[harness] Task #42 ✅",
    "body": "✅ タスク完了\n..."
  }
}
```

### 添付ファイル対応（将来拡張）

`result` フィールドに Markdown コンテンツが入るため、MailMindHub 側で:
- Markdown → PDF 変換して添付
- Markdown → PPTX 変換して添付

などの対応が可能になります。

---

## 後方互換性

既存の明示コマンド（`/generate`、`/review`、`/fix`）は引き続き動作します。ルール優先順位の先頭に配置されているため、プレフィックスを使用した従来の指示はそのまま動作します。

---

## 制限事項と今後の課題

| 項目 | 現状 | 今後の対応案 |
|---|---|---|
| PPT/PDF バイナリ生成 | Markdown 形式で出力 | MailMindHub 側で変換 or `python-pptx` 対応 |
| ファイル操作のパス | `/tmp/harness-{id}` のみ | `project.path` 経由でユーザーディレクトリに対応 |
| 添付ファイル返信 | 未対応 | Webhook ペイロードへの `attachments` フィールド追加 |
| 多言語判定 | 日・中・英の基本キーワード | LLM による意図分類への切り替え |

---

*ドキュメントバージョン: 2.1.0 | 作成日: 2026-04-13*
