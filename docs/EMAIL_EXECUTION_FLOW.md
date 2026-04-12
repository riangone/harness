# MailMindHub 指令执行与返回流程

## 整体流程图

```
MailMindHub（邮件接收）
    │
    │  POST /api/v1/tasks/from-email
    │  { subject, body, from_addr, callback_url }
    ▼
[external_api.py: create_task_from_email()]
    │
    │  1. MailGateway.parse_email_to_task() 路由判断
    │     - subject + body 与 routing_rules（正则表达式）匹配
    │     - /generate → code_generation pipeline
    │     - /review   → code_review pipeline
    │     - /fix      → bug_fix pipeline
    │     - /help     → 返回帮助文本（不创建任务）
    │
    │  2. 将 Task 记录 INSERT 到 DB
    │     - source="email", pipeline_mode=True
    │     - task_meta 以 JSON 保存 callback_url 和 from_addr
    │
    │  3. 立即向 MailMindHub 返回 202（附带 task_id）
    │
    │  4. 通过 BackgroundTasks 启动 _execute_task_with_callback()
    ▼
[executor.py: _execute_pipeline()]
    │
    │  Phase 1 — planning（由 Claude 负责）
    │    claude -p "..." → 生成 work_dir/plan.md
    │
    │  Phase 2 — generating（优先使用 Qwen，最多 retry 3 次）
    │    qwen -y "..."  → 生成实现代码
    │
    │  Phase 3 — evaluating（由 Claude 负责）
    │    claude -p "..." → 生成 work_dir/eval-report.md
    │    解析 eval-report.md 中的 "VERDICT: PASS/FAIL"
    │
    │    FAIL → 将 eval-report.md 的问题点反馈给 Generator → retry
    │    PASS → Task.status = completed
    ▼
[external_api.py: _send_webhook_callback()]
    │
    │  1. 从 task_meta 中取出 callback_url
    │  2. MailGateway.format_task_complete_response()
    │     格式化邮件正文（subject + body）
    │  3. POST callback_url
    │     {
    │       task_id, status, title, result,
    │       from_addr,        ← MailMindHub 用于确定回复地址
    │       runs[],           ← 各阶段日志
    │       email_content: { subject, body }  ← 可直接用于发送邮件
    │     }
    ▼
MailMindHub（接收 email_content，向 from_addr 发送回复邮件）
```

## 关键实现细节

### 路由规则

配置文件：`config/gateway.yaml`，若不存在则使用 `MailGateway._default_config()` 的默认规则。

将 subject 和 body 拼接后进行正则匹配。若无匹配规则，返回 `/help` 文本，不创建任务。

| 命令 | Pipeline |
|------|----------|
| `/generate <描述>` 或 `/gen` | `code_generation` |
| `/review <描述>` | `code_review` |
| `/fix <描述>` | `bug_fix` |
| `/help` 或 `?` | 返回帮助文本 |

### 阶段间的上下文隔离

各阶段之间**只通过文件传递上下文**，不共享内存：

| 文件 | 生成者 | 使用者 |
|------|--------|--------|
| `work_dir/plan.md` | Planner (Claude) | Generator |
| `work_dir/eval-report.md` | Evaluator (Claude) | 下一次 attempt 的 Generator |

### Webhook 回调结构（`CallbackPayload`）

```json
{
  "task_id": 123,
  "status": "completed",
  "title": "[email] 任务标题",
  "result": "执行结果",
  "from_addr": "user@example.com",
  "runs": [
    {
      "phase": "planning",
      "status": "completed",
      "log_summary": "...",
      "agent": "Claude Planner",
      "attempt": 1,
      "eval_verdict": null
    },
    ...
  ],
  "email_content": {
    "subject": "[harness] Task #123 ✅",
    "body": "✅ 任务完成\n..."
  }
}
```

- `from_addr`：MailMindHub 用于确定将回复发往哪个地址
- `email_content.body`：已格式化完毕的邮件正文，MailMindHub 可直接使用

### 失败处理

- Generator 连续 3 次 attempt 全部 FAIL，或 Generator 本身执行失败时，Task 状态置为 `failed`
- 即使失败，也会触发 Webhook 回调（`status: "failed"`），MailMindHub 可据此通知用户

## 相关源码位置

| 功能 | 文件 | 关键函数 |
|------|------|----------|
| 邮件任务入口 | `webui/app/routers/external_api.py` | `create_task_from_email()` |
| Webhook 回调发送 | `webui/app/routers/external_api.py` | `_send_webhook_callback()` |
| Pipeline 执行 | `webui/app/services/executor.py` | `_execute_pipeline()` |
| 邮件路由解析 | `core/gateway/mail.py` | `MailGateway.parse_email_to_task()` |
| 邮件响应格式化 | `core/gateway/mail.py` | `MailGateway.format_task_complete_response()` |
| 路由规则配置 | `config/gateway.yaml` | `mail.routing_rules` |
