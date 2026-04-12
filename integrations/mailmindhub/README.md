# MailMindHub ↔ harness 集成指南

## 📋 架构

```
邮件 → MailMindHub → harness API → 任务执行 → 结果返回 → MailMindHub 回复邮件
```

## 🔧 配置步骤

### 1️⃣ 启动 harness WebUI

确保 harness WebUI 在运行（默认端口 7500）：

```bash
cd /home/ubuntu/ws/harness
python -m uvicorn webui.app.main:app --host 0.0.0.0 --port 7500
```

### 2️⃣ 配置 harness 的邮件网关（可选）

编辑 `config/gateway.yaml`：

```yaml
mail:
  enabled: true
  provider: mailmindhub  # 使用 MailMindHub 模式
  
  mailmindhub:
    api_endpoint: http://localhost:7000  # MailMindHub WebUI 地址
    auth:
      token_env: MAILMINDHUB_TOKEN
```

### 3️⃣ 在 MailMindHub 中集成 harness

#### 方法 A：作为 AI 后端（推荐）

编辑 MailMindHub 的 `core/config.py`，在 `AI_BACKENDS` 中添加：

```python
"harness": {
    "type": "api_openai",  # 伪装成 OpenAI 兼容 API
    "api_key": os.environ.get("HARNESS_API_TOKEN", ""),
    "model": "harness-pipeline",
    "url": "http://localhost:7500/api/external/create_task",
    "label": "Harness 多角色管道",
    "env_key": "HARNESS_API_TOKEN"
}
```

**注意**：由于 MailMindHub 的 AI 调用是同步的，而 harness 任务是异步的，这种方法需要额外适配。

#### 方法 B：作为独立任务处理器（推荐⭐）

在 MailMindHub 的 `email_daemon.py` 中，修改 `process_email` 函数，检测特定关键词后调用 harness：

```python
# 在 process_email 开头添加
HARNESS_KEYWORDS = {"review", "generate", "gen", "fix", "build", "create"}

def _should_route_to_harness(em: dict) -> bool:
    """检测是否应该转给 harness 处理"""
    subject = (em.get("subject") or "").strip().lower()
    body = (em.get("body") or "").strip().lower()
    text = f"{subject} {body}"
    return any(kw in text for kw in HARNESS_KEYWORDS)
```

然后在邮件处理逻辑中添加：

```python
# 在 _process_email_impl 开头添加
if _should_route_to_harness(em):
    log.info("🔄 转给 harness 处理")
    try:
        from integrations.mailmindhub.harness_backend import call_harness
        
        title = em.get("subject", "邮件任务")
        prompt = f"发件人：{em['from']}\n主题：{em['subject']}\n\n{em.get('body', '')}"
        
        result = call_harness(title, prompt, pipeline_mode=True)
        
        # 回复邮件
        send_reply(MAILBOXES[mailbox_name], em["from_email"], 
                   f"✅ harness 完成: {title}", result, 
                   em.get("message_id"), lang="zh")
        
        mark_processed_id(em["id"])
        save_processed_ids(PROCESSED_IDS_PATH, processed_ids)
        return  # 不再继续 MailMindHub 的处理
    except Exception as e:
        log.error(f"harness 调用失败: {e}")
        # 继续走 MailMindHub 默认流程
```

### 4️⃣ 设置环境变量

在 MailMindHub 的 `.env` 中添加：

```bash
# harness 集成
HARNESS_API_URL=http://localhost:7500
HARNESS_API_TOKEN=  # 留空表示不验证（开发模式）
HARNESS_POLL_INTERVAL=10  # 轮询间隔（秒）
HARNESS_MAX_WAIT=600  # 最大等待时间（秒）
```

## 🚀 使用方式

### 从邮件触发 harness 任务

发送邮件到 MailMindHub 监听的邮箱，邮件内容包含以下关键词之一：

| 关键词 | 触发管道 |
|--------|----------|
| `review` | 代码审查 |
| `generate` / `gen` | 代码生成 |
| `fix` | Bug 修复 |
| `build` | 构建任务 |
| `create` | 创建任务 |

### 示例邮件

```
主题: generate a todo app

正文:
用 Python FastAPI 创建一个待办事项应用，包含：
- CRUD 接口
- SQLite 数据库
- 基本的 HTML 界面
```

MailMindHub 收到后会：
1. 检测到 `generate` 关键词
2. 调用 harness API 创建任务
3. harness 执行多角色管道（规划→生成→评估）
4. 完成后将结果回复到邮箱

## 📊 API 端点

harness 提供的外部 API：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/external/create_task` | POST | 创建并执行任务 |
| `/api/external/task_status/{id}` | GET | 查询任务状态 |
| `/api/external/health` | GET | 健康检查 |

### 创建任务示例

```bash
curl -X POST http://localhost:7500/api/external/create_task \
  -H "Content-Type: application/json" \
  -d '{
    "title": "测试任务",
    "prompt": "创建一个简单的 Python 脚本",
    "pipeline_mode": true
  }'
```

返回：
```json
{
  "task_id": 1,
  "status": "pending",
  "message": "任务已创建并开始执行"
}
```

### 查询状态示例

```bash
curl http://localhost:7500/api/external/task_status/1
```

返回：
```json
{
  "task_id": 1,
  "status": "completed",
  "title": "测试任务",
  "result": "任务执行完成...",
  "runs": [
    {
      "phase": "planning",
      "status": "completed",
      "result": "...",
      "agent": "Planner"
    }
  ]
}
```

## ⚠️ 注意事项

1. **数据库迁移**：首次运行需要添加新字段
   ```bash
   # 在 harness 目录执行
   sqlite3 data/harness.db "ALTER TABLE tasks ADD COLUMN source TEXT DEFAULT 'webui';"
   sqlite3 data/harness.db "ALTER TABLE tasks ADD COLUMN result TEXT DEFAULT '';"
   ```

2. **端口冲突**：确保 harness WebUI 端口（默认 7500）未被占用

3. **超时设置**：harness 任务可能耗时较长，确保 MailMindHub 的超时设置足够

## 🔍 故障排查

### harness API 无响应
```bash
# 检查 harness 是否运行
curl http://localhost:7500/api/external/health

# 查看日志
tail -f /home/ubuntu/ws/harness/webui/logs/*.log
```

### MailMindHub 未调用 harness
```bash
# 查看 MailMindHub 日志
tail -f /home/ubuntu/ws/MailMind/daemon.log

# 检查关键词是否匹配
grep -i "harness" /home/ubuntu/ws/MailMind/daemon.log
```

### 任务卡在 pending 状态
```bash
# 查看任务状态
curl http://localhost:7500/api/external/task_status/<task_id>

# 检查 harness 数据库
sqlite3 /home/ubuntu/ws/harness/data/harness.db "SELECT * FROM tasks ORDER BY id DESC LIMIT 5;"
```
