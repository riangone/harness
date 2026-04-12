# Harness API 协议文档

> 供 MailMindHub 对接的 HTTP API 规范
> 版本: 2.0.0
> 日期: 2026-04-12

---

## 架构概览

```
用户 ──邮件──→ MailMindHub
                   │
            判断任务类型
                   │
        ┌──────────┴──────────┐
        │                     │
   简单对话             复杂Pipeline任务
   (MailMindHub              │
    自己AI处理)               ▼
                      harness API (HTTP)
                      POST /api/v1/tasks
                      │
                      Pipeline执行
                      (多模型协作)
                      │
                      Webhook 回调通知
                      POST {callback_url}
                      │
                      ▼
                   MailMindHub
                   回复用户邮件
```

---

## 基础信息

| 项目 | 值 |
|------|-----|
| 基础 URL | `http://localhost:7500`（独立模式）或 `https://mah.0101.click`（嵌入模式） |
| 认证方式 | Header: `X-API-Key: <token>` |
| 数据格式 | JSON |
| 字符编码 | UTF-8 |

### 认证

所有 API 端点都需要 `X-API-Key` Header。如果服务端未设置 `HARNESS_API_TOKEN` 环境变量，则开发模式下所有请求都被允许（无需认证）。

```bash
curl -H "X-API-Key: your-secret-token" http://localhost:7500/api/v1/health
```

---

## API 端点

### 1. 健康检查

```
GET /api/v1/health
```

**响应：**
```json
{
  "status": "ok",
  "service": "harness",
  "version": "2.0.0"
}
```

---

### 2. 创建任务（通用）

```
POST /api/v1/tasks
```

**请求体：**
```json
{
  "title": "代码生成任务",
  "prompt": "写一个快速排序函数",
  "success_criteria": "1. 时间复杂度 O(n log n)\n2. 包含单元测试",
  "pipeline_mode": true,
  "agent_id": null,
  "project_id": null,
  "callback_url": "http://mailmindhub:8080/api/harness/callback",
  "source": "email",
  "metadata": {
    "from_addr": "user@example.com",
    "subject": "/generate 写一个快速排序"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | ✅ | 任务标题 |
| prompt | string | ✅ | 任务提示/描述 |
| success_criteria | string | ❌ | 成功标准（用于 Evaluator） |
| pipeline_mode | boolean | ❌ | 是否使用 Pipeline 模式（默认 true） |
| agent_id | int | ❌ | 指定 Agent ID（null = 自动选择） |
| project_id | int | ❌ | 项目 ID |
| callback_url | string | ❌ | **Webhook 回调地址**。任务完成后，harness 会 POST 结果到此 URL |
| source | string | ❌ | 任务来源（email / api / cli） |
| metadata | object | ❌ | 额外元数据 |

**响应（200）：**
```json
{
  "task_id": 42,
  "status": "pending",
  "message": "任务已创建，正在后台执行"
}
```

---

### 3. 从邮件创建任务

```
POST /api/v1/tasks/from-email
```

MailMindHub 收到用户邮件后，调用此端点让 harness 自动解析邮件内容并创建对应任务。

**请求体：**
```json
{
  "subject": "/generate 写一个快速排序函数",
  "body": "/generate 写一个快速排序函数，要求支持泛型",
  "from_addr": "user@example.com",
  "callback_url": "http://mailmindhub:8080/api/harness/callback"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| subject | string | ✅ | 邮件主题 |
| body | string | ✅ | 邮件正文 |
| from_addr | string | ✅ | 发件人地址 |
| callback_url | string | ❌ | Webhook 回调地址 |

**响应（200）— 成功解析：**
```json
{
  "task_id": 43,
  "status": "pending",
  "message": "任务已创建，Pipeline: code_generation"
}
```

**响应（200）— 无法识别的命令：**
```json
{
  "task_id": null,
  "status": "unknown_command",
  "message": "无法识别的命令，已生成帮助信息",
  "help_sent": true
}
```

> `help_sent: true` 表示 harness 已生成帮助文本，MailMindHub 应该将其回复给用户。

---

### 4. 查询任务状态

```
GET /api/v1/tasks/{task_id}
```

**响应（200）：**
```json
{
  "task_id": 42,
  "status": "completed",
  "title": "代码生成任务",
  "prompt": "写一个快速排序函数",
  "result": "def quick_sort(arr): ...",
  "source": "email",
  "created_at": "2026-04-12 10:00:00",
  "completed_at": "2026-04-12 10:02:30",
  "runs": [
    {
      "phase": "planning",
      "status": "completed",
      "result": null,
      "agent": "Claude Planner",
      "attempt": 1,
      "eval_verdict": null,
      "started_at": "2026-04-12 10:00:01",
      "finished_at": "2026-04-12 10:00:15"
    },
    {
      "phase": "generating",
      "status": "completed",
      "result": "def quick_sort(arr): ...",
      "agent": "Qwen Generator",
      "attempt": 1,
      "eval_verdict": null,
      "started_at": "2026-04-12 10:00:16",
      "finished_at": "2026-04-12 10:01:30"
    },
    {
      "phase": "evaluating",
      "status": "completed",
      "result": null,
      "agent": "Claude Evaluator",
      "attempt": 1,
      "eval_verdict": "PASS",
      "started_at": "2026-04-12 10:01:31",
      "finished_at": "2026-04-12 10:02:30"
    }
  ]
}
```

**任务状态值：**
| 状态 | 说明 |
|------|------|
| pending | 已创建，等待执行 |
| running | 正在执行 |
| completed | 执行成功 |
| failed | 执行失败 |

---

### 5. 查询任务列表

```
GET /api/v1/tasks?limit=20&offset=0&status=completed&source=email
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | int | ❌ | 返回数量（默认 20） |
| offset | int | ❌ | 偏移量 |
| status | string | ❌ | 按状态过滤 |
| source | string | ❌ | 按来源过滤（email / api） |

**响应：**
```json
{
  "tasks": [
    {
      "task_id": 42,
      "title": "代码生成任务",
      "status": "completed",
      "source": "email",
      "created_at": "2026-04-12 10:00:00"
    }
  ],
  "total": 1
}
```

---

### 6. 取消任务

```
POST /api/v1/tasks/{task_id}/cancel
```

**响应（200）：**
```json
{
  "task_id": 42,
  "status": "cancelled",
  "message": "任务已取消"
}
```

---

### 7. 查询可用 Agent

```
GET /api/v1/agents
```

**响应：**
```json
{
  "agents": [
    {
      "id": 1,
      "name": "Claude Planner",
      "role": "planner",
      "cli_command": "claude",
      "priority": 10
    },
    {
      "id": 2,
      "name": "Qwen Generator",
      "role": "generator",
      "cli_command": "qwen",
      "priority": 10
    }
  ]
}
```

---

### 8. 测试 Webhook 回调

```
POST /api/v1/callback/test
Headers: X-Callback-URL: http://mailmindhub:8080/api/harness/callback
```

向指定的回调 URL 发送测试 payload。

**响应（200）：**
```json
{
  "status": "ok",
  "response_code": 200,
  "url": "http://mailmindhub:8080/api/harness/callback"
}
```

---

## Webhook 回调协议

当任务创建时传入了 `callback_url`，harness 在任务完成（completed 或 failed）后会主动 POST 结果到该 URL。

### 回调 Payload

```json
{
  "task_id": 42,
  "status": "completed",
  "title": "代码生成任务",
  "result": "def quick_sort(arr): ...",
  "runs": [
    {
      "phase": "planning",
      "status": "completed",
      "result": null,
      "log_summary": "...",
      "agent": "Claude Planner",
      "attempt": 1,
      "eval_verdict": null
    },
    {
      "phase": "generating",
      "status": "completed",
      "result": "def quick_sort(arr): ...",
      "log_summary": "...",
      "agent": "Qwen Generator",
      "attempt": 1,
      "eval_verdict": null
    },
    {
      "phase": "evaluating",
      "status": "completed",
      "result": null,
      "log_summary": "...",
      "agent": "Claude Evaluator",
      "attempt": 1,
      "eval_verdict": "PASS"
    }
  ],
  "email_content": {
    "subject": "[harness] Task #42 ✅",
    "body": "✅ **任务完成**\n\n**任务**: 代码生成任务\n**耗时**: 150秒\n**状态**: ✅ Success\n\n**执行步骤**:\n✅ planning (Claude Planner)\n✅ generating (Qwen Generator)\n✅ evaluating (Claude Evaluator)\n\n---\n💡 回复此邮件可继续对话"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | int | 任务 ID |
| status | string | `completed` 或 `failed` |
| title | string | 任务标题 |
| result | string | 最终结果文本 |
| runs | array | 执行步骤详情 |
| email_content | object | **格式化好的邮件内容**，MailMindHub 可直接用来回复用户 |

### email_content 结构

```json
{
  "subject": "[harness] Task #42 ✅",
  "body": "✅ **任务完成**\n\n..."
}
```

harness 已经根据模板格式化好了邮件主题和正文，MailMindHub 只需将其发送给用户即可。

### MailMindHub 回调端点要求

MailMindHub 需要提供一个 HTTP POST 端点来接收此回调：

```
POST {callback_url}
Content-Type: application/json
```

MailMindHub 收到回调后：
1. 从 `email_content` 中获取 subject 和 body
2. 回复对应用户的邮件
3. 返回 `200 OK` 给 harness

---

## 错误处理

所有 API 端点在出错时返回标准 HTTP 状态码和错误信息：

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 认证失败（API Token 无效或缺失） |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
| 502 | Webhook 回调测试失败 |

**错误响应格式：**
```json
{
  "detail": "Task 999 not found"
}
```

---

## 调用流程示例

### 场景：用户发邮件 → harness 处理 → 回复邮件

```
1. 用户发邮件到 MailMindHub：
   Subject: /generate 写一个快速排序函数

2. MailMindHub → harness（创建任务）：
   POST /api/v1/tasks/from-email
   {
     "subject": "/generate 写一个快速排序函数",
     "body": "/generate 写一个快速排序函数",
     "from_addr": "user@example.com",
     "callback_url": "http://mailmindhub:8080/api/harness/callback"
   }

3. harness 立即返回：
   { "task_id": 42, "status": "pending", "message": "任务已创建，正在后台执行" }

4. harness 后台执行 Pipeline（planner → generator → evaluator）...

5. harness → MailMindHub（Webhook 回调）：
   POST http://mailmindhub:8080/api/harness/callback
   {
     "task_id": 42,
     "status": "completed",
     "result": "def quick_sort(arr): ...",
     "email_content": {
       "subject": "[harness] Task #42 ✅",
       "body": "✅ **任务完成**\n\n..."
     }
   }

6. MailMindHub → 用户（回复邮件）：
   Subject: [harness] Task #42 ✅
   Body: ✅ **任务完成**\n\n...
```

---

## 启动方式

### 独立模式
```bash
# 作为独立服务启动
uvicorn harness_api:app --host 0.0.0.0 --port 7500 --reload

# 设置 API Token
export HARNESS_API_TOKEN="your-secret-token"
```

### 嵌入模式（与 WebUI 同一进程）
```bash
# WebUI 已自动包含 external_api 路由
# API 端点通过 /api/v1/* 访问
cd webui && ./start.sh
```

---

## 向后兼容

旧的 API 端点（`/api/external/create_task` 和 `/api/external/task_status/{id}`）仍然保留在 WebUI 中，但新的集成推荐使用 `/api/v1/*` 系列端点。
