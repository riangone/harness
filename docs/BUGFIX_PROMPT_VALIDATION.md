# バグ修正レポート: 必須パラメーター `prompt` バリデーションエラー

> バグ ID: harness-validation-001
> 修正コミット: `730cdaf`
> 修正日: 2026-04-13
> 深刻度: **高**（メール経由の全タスク作成が失敗する場合あり）

---

## 症状

MailMindHub からメールを送信すると、以下のエラーが返却される。

```
参数验证失败: 缺少必填参数: prompt
```

または FastAPI デフォルト形式で：

```json
{
  "detail": [
    {
      "loc": ["body", "prompt"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

**再現手順**:

```bash
# ケース1: /api/v1/tasks に title のみ送信
curl -X POST http://localhost:7500/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "2026年のAI・LLM技術トレンドを調査してください"}'
# → 422 Unprocessable Entity（修正前）

# ケース2: /api/v1/tasks/from-email に body なしで送信
curl -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{"subject": "AIトレンドを調査して", "from_addr": "user@example.com"}'
# → 422 Unprocessable Entity（修正前）
```

---

## 根本原因

**エラーは harness 側の API 定義に起因**。MailMindHub はエラーを整形して表示していただけ。

### 原因 1: `TaskCreateRequest.prompt` が必須フィールド

```python
# 修正前（webui/app/routers/external_api.py）
class TaskCreateRequest(BaseModel):
    title: str = Field(..., description="任务标题")   # 必須
    prompt: str = Field(..., description="任务提示")  # 必須 ← 問題
```

MailMindHub が `/api/v1/tasks` を呼ぶ際に `title` だけ送ると、Pydantic が `prompt` の欠落を検出して HTTP 422 を返す。

### 原因 2: `EmailTaskRequest.body` が必須フィールド

```python
# 修正前
class EmailTaskRequest(BaseModel):
    subject: str = Field(...)
    body: str = Field(...)       # 必須 ← 問題
    from_addr: str = Field(...)  # 必須 ← 問題
```

件名だけのメール（本文なし）や `from_addr` が省略されたリクエストが全て失敗していた。

### 原因 3: カスタムエラーハンドラーなし

FastAPI デフォルトの 422 レスポンスは構造が複雑で、MailMindHub 側でのデバッグが困難だった。

---

## 修正内容

### 修正ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `webui/app/routers/external_api.py` | `TaskCreateRequest` / `EmailTaskRequest` フィールドを Optional 化 |
| `harness_api.py` | カスタム 422 バリデーションエラーハンドラー追加 |
| `webui/app/main.py` | 同上（WebUI モード用） |

---

### 修正 1: `TaskCreateRequest` — title/prompt 相互補完

```python
# 修正後
class TaskCreateRequest(BaseModel):
    title: Optional[str] = Field(None, description="任务标题（省略時は prompt 先頭80文字）")
    prompt: Optional[str] = Field(None, description="任务提示（省略時は title を使用）")
    # ... 他フィールドは変更なし
```

エンドポイント内で相互補完ロジックを追加：

```python
prompt = (req.prompt or "").strip()
title  = (req.title  or "").strip()

if not prompt and not title:
    raise HTTPException(422, detail={
        "error": "validation_error",
        "message": "title または prompt のいずれかは必須です",
        "hint": '例: {"title": "タスク名"} または {"prompt": "指示内容"}'
    })

if not prompt: prompt = title        # title だけ → prompt として使用
if not title:  title  = prompt[:80]  # prompt だけ → 先頭80文字をタイトルに
```

**動作変化**:

| リクエスト | 修正前 | 修正後 |
|---|---|---|
| `{"title": "調査して"}` | 422 エラー | ✅ `prompt = "調査して"` で実行 |
| `{"prompt": "詳細な調査..."}` | 422 エラー（title も必須だった場合） | ✅ `title = "詳細な調査..."[:80]` |
| `{"title": "調査", "prompt": "詳細..."}` | ✅ 正常 | ✅ 正常（変化なし） |
| `{}` | 422 エラー | 422 エラー（ただし明確なメッセージ付き） |

---

### 修正 2: `EmailTaskRequest` — body/from_addr を Optional 化

```python
# 修正後
class EmailTaskRequest(BaseModel):
    subject:      str           = Field(...,  description="邮件主题（必須）")
    body:         Optional[str] = Field("",   description="邮件正文（省略可、デフォルト空文字）")
    from_addr:    Optional[str] = Field(None, description="发件人地址（省略可）")
    callback_url: Optional[str] = Field(None, description="Webhook 回调地址")
```

エンドポイント内で `None` を正規化：

```python
body      = req.body      or ""
from_addr = req.from_addr or ""
```

**動作変化**:

| リクエスト | 修正前 | 修正後 |
|---|---|---|
| `{"subject": "AIを調査して"}` | 422 エラー（body, from_addr 必須） | ✅ 正常動作 |
| `{"subject": "...", "body": "..."}` | 422 エラー（from_addr 必須） | ✅ 正常動作 |
| `{"subject": "...", "body": "...", "from_addr": "..."}` | ✅ 正常 | ✅ 正常（変化なし） |

---

### 修正 3: タスクコンテンツ空文字ガード

本文も件名からも内容を抽出できなかった場合に明確なエラーを返す：

```python
task_input = (task_data.get('input') or "").strip()
if not task_input:
    task_input = req.subject.strip()
if not task_input:
    return EmailTaskResponse(
        status="error",
        message="タスク内容を抽出できませんでした。件名か本文に具体的な指示を記入してください。",
        help_sent=False
    )
```

---

### 修正 4: カスタム 422 エラーハンドラー

```python
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # ...
    return JSONResponse(status_code=422, content={
        "error": "validation_error",
        "missing_fields": ["prompt"],           # ← 欠落フィールドを明示
        "message": "必須フィールドが不足しています: prompt",
        "hint": "title か prompt のいずれかを指定してください。"
    })
```

**エラーレスポンス変化**:

```json
// 修正前（FastAPI デフォルト）
{
  "detail": [{"loc": ["body", "prompt"], "msg": "Field required", "type": "missing"}]
}

// 修正後（カスタムハンドラー）
{
  "error": "validation_error",
  "missing_fields": ["prompt"],
  "message": "必須フィールドが不足しています: prompt",
  "hint": "title か prompt のいずれかを指定してください。"
}
```

---

## 修正後の動作確認

### テスト 1: title のみで /api/v1/tasks を呼ぶ

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "2026年のAI・LLM技術トレンドを調査してください"}' | python3 -m json.tool
```

**期待レスポンス**:
```json
{
  "task_id": 1,
  "status": "pending",
  "message": "タスクが作成されました"
}
```

### テスト 2: /api/v1/tasks/from-email に subject のみ送信

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{"subject": "2026年のAI・LLM技術トレンドを調査してください"}' | python3 -m json.tool
```

**期待レスポンス**:
```json
{
  "task_id": 2,
  "status": "pending",
  "message": "タスクが作成されました。Pipeline: research"
}
```

### テスト 3: 両方空でエラーメッセージ確認

```bash
curl -s -X POST http://localhost:7500/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool
```

**期待レスポンス（422）**:
```json
{
  "error": "validation_error",
  "message": "title または prompt のいずれかは必須です",
  "hint": "例: {\"title\": \"タスク名\"} または {\"prompt\": \"指示内容\"}"
}
```

---

## MailMindHub 側の推奨対応

この修正により、MailMindHub は以下いずれの形式でもリクエストを送信できるようになりました：

```bash
# 方法 A: /tasks/from-email（推奨）— subject だけで OK
POST /api/v1/tasks/from-email
{"subject": "AIトレンドを調査して"}

# 方法 B: /tasks/from-email — 全フィールド
POST /api/v1/tasks/from-email
{"subject": "件名", "body": "本文", "from_addr": "user@example.com", "callback_url": "..."}

# 方法 C: /tasks — title だけ
POST /api/v1/tasks
{"title": "タスク名"}

# 方法 D: /tasks — 完全形式
POST /api/v1/tasks
{"title": "タスク名", "prompt": "詳細な指示", "callback_url": "..."}
```

---

## 影響範囲

この修正は **後方互換** です。既存の呼び出し（`title` と `prompt` の両方を指定）は変更なく動作します。

---

*修正レポートバージョン: 1.0 | 作成日: 2026-04-13*
