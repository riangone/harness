# 📋 MailMindHub ↔ harness 集成 - 配置清单

## ✅ 已完成的工作

### 1. harness 端
- ✅ 创建外部 API 端点 (`webui/app/routers/external_api.py`)
  - `POST /api/external/create_task` - 创建并执行任务
  - `GET /api/external/task_status/{id}` - 查询任务状态
  - `GET /api/external/health` - 健康检查

- ✅ 更新 Task 模型 (`webui/app/models.py`)
  - 添加 `source` 字段 - 任务来源 (webui/api/email)
  - 添加 `result` 字段 - 任务执行结果

- ✅ 注册路由 (`webui/app/main.py`)

- ✅ 数据库迁移 (`scripts/migrate_db.sh`)
  - 已成功添加 `source` 和 `result` 字段

### 2. MailMindHub 端
- ✅ 创建集成脚本 (`integrations/mailmindhub/harness_backend.py`)
  - `HarnessClient` 类 - harness API 客户端
  - `call_harness()` 函数 - 便捷调用函数

- ✅ 配置文档 (`integrations/mailmindhub/README.md`)

---

## 🔧 接下来需要你做的事

### 步骤 1：安装 harness 依赖

```bash
cd /home/ubuntu/ws/harness/webui
pip3 install -r requirements.txt
```

### 步骤 2：启动 harness WebUI

```bash
cd /home/ubuntu/ws/harness
bash scripts/start_harness.sh
# 或者手动启动
cd /home/ubuntu/ws/harness && uvicorn webui.app.main:app --host 0.0.0.0 --port 7500
```

### 步骤 3：测试 harness API

```bash
# 健康检查
curl http://localhost:7500/api/external/health

# 创建测试任务
curl -X POST http://localhost:7500/api/external/create_task \
  -H "Content-Type: application/json" \
  -d '{
    "title": "测试任务",
    "prompt": "创建一个简单的 Python Hello World 脚本",
    "pipeline_mode": false
  }'
```

### 步骤 4：在 MailMindHub 中集成 harness

你有两种选择：

#### 选择 A：修改 MailMindHub 的 email_daemon.py（推荐）

编辑 `/home/ubuntu/ws/MailMind/email_daemon.py`，在 `process_email` 函数开头添加路由逻辑：

```python
# 在文件开头添加
HARNESS_KEYWORDS = {"review", "generate", "gen", "fix", "build", "create"}
HARNESS_API_URL = os.environ.get("HARNESS_API_URL", "http://localhost:7500")

def _should_route_to_harness(em: dict) -> bool:
    """检测是否应该转给 harness 处理"""
    subject = (em.get("subject") or "").strip().lower()
    body = (em.get("body") or "").strip().lower()
    text = f"{subject} {body}"
    return any(kw in text for kw in HARNESS_KEYWORDS)

# 在 _process_email_impl 函数开头添加
def _process_email_impl(mailbox_name, ai_name, backend, em):
    # ===== 添加这段代码 =====
    if _should_route_to_harness(em):
        log.info("🔄 转给 harness 处理")
        try:
            import sys
            sys.path.insert(0, "/home/ubuntu/ws/harness/integrations/mailmindhub")
            from harness_backend import call_harness
            
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
            import traceback
            log.error(f"harness 调用失败: {e}\n{traceback.format_exc()}")
            # 继续走 MailMindHub 默认流程
    # ===== 添加结束 =====
    
    # 下面是原有的逻辑...
```

#### 选择 B：作为 AI 后端

编辑 MailMindHub 的 `core/config.py`，在 `AI_BACKENDS` 中添加：

```python
# 在 AI_BACKENDS 字典中添加
"harness": {
    "type": "custom",
    "endpoint": "http://localhost:7500/api/external/create_task",
    "api_key": os.environ.get("HARNESS_API_TOKEN", ""),
    "label": "Harness 多角色管道",
}
```

但这种方式需要修改 MailMindHub 的 AI 调用逻辑，比较复杂。

### 步骤 5：设置环境变量

在 MailMindHub 的 `.env` 文件中添加：

```bash
# harness 集成
HARNESS_API_URL=http://localhost:7500
HARNESS_API_TOKEN=
HARNESS_POLL_INTERVAL=10
HARNESS_MAX_WAIT=600
```

### 步骤 6：重启 MailMindHub

```bash
cd /home/ubuntu/ws/MailMind
# 停止现有进程
./manage.sh stop  # 或者 kill 进程
# 重新启动
./manage.sh start
```

---

## 🧪 测试流程

1. 发送邮件到 MailMindHub 监听的邮箱
2. 邮件主题或正文包含关键词（如 `generate`、`review`、`fix`）
3. MailMindHub 检测到关键词，调用 harness API
4. harness 创建任务并执行（多角色管道）
5. 完成后结果返回给 MailMindHub
6. MailMindHub 回复邮件到发件人

---

## 📊 架构流程图

```
用户发邮件
    ↓
MailMindHub 收到邮件
    ↓
检测关键词 (review/generate/fix 等)
    ↓
调用 harness API (POST /api/external/create_task)
    ↓
harness 创建 Task → 执行管道
    ├─ Planner (规划)
    ├─ Generator (生成)
    └─ Evaluator (评估)
    ↓
任务完成，写入 result
    ↓
harness 返回结果给 MailMindHub
    ↓
MailMindHub 回复邮件给用户
```

---

## ⚠️ 注意事项

1. **端口**：harness 默认 7500，确保未被占用
2. **数据库**：已迁移，添加了 `source` 和 `result` 字段
3. **超时**：harness 任务可能耗时较长（几分钟），`MAX_WAIT` 设大一点
4. **认证**：开发模式 `HARNESS_API_TOKEN` 留空表示不验证

---

## 🆘 故障排查

### harness 启动失败
```bash
cd /home/ubuntu/ws/harness/webui
pip3 install -r requirements.txt
uvicorn webui.app.main:app --host 0.0.0.0 --port 7500
```

### API 无响应
```bash
curl http://localhost:7500/api/external/health
```

### MailMindHub 未调用 harness
```bash
tail -f /home/ubuntu/ws/MailMind/daemon.log | grep -i harness
```
