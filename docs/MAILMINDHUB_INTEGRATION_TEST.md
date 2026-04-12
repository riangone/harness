# MailMindHub × harness 联动测试指南

> 本文档提供具体的邮件测试示例，用于验证 MailMindHub 和 harness 的完整联动流程。
> 创建日期: 2026-04-12

---

## 已知问题与修复

### 问题：任务完成后未收到回调邮件

**症状**: 发送邮件后收到 "🤖 Harness 任务已提交 #N"，但之后没有收到完成通知邮件。

**根因**: SQLAlchemy 的 Declarative 基类保留了 `metadata` 属性名（指向 `MetaData()` 对象），导致自定义的 metadata 列无法正确读写。这导致：
1. `callback_url` 和 `from_addr` 未保存到数据库
2. 任务完成后 `_send_webhook_callback` 找不到回调地址
3. `prompt` 可能为空（取决于 email 解析结果）

**修复** (2026-04-12):
1. `webui/app/models.py`: 将列定义改为 `task_meta = Column("metadata", Text, ...)` 避免命名冲突
2. `webui/app/routers/external_api.py`: 所有 `task.metadata` 引用改为 `task.task_meta`
3. 数据库迁移: `ALTER TABLE tasks ADD COLUMN metadata TEXT;`

**验证修复**:
```bash
# 创建测试任务
curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{"subject":"/generate test","body":"/generate test","from_addr":"t@t.com","callback_url":"http://localhost:9999/cb"}'

# 检查 metadata 是否正确写入
sqlite3 webui/harness.db "SELECT id, status, substr(metadata,1,50) FROM tasks ORDER BY id DESC LIMIT 1;"
# 应显示包含 callback_url 的 JSON 数据
```

---

## 前置条件

### 1. 服务状态检查

```bash
# 检查 harness API 是否运行
curl http://localhost:7500/api/v1/health
# 预期返回: {"status":"ok","service":"harness","version":"2.0.0"}

# 检查 MailMindHub 是否运行
# （根据实际部署方式检查）

# 测试 Webhook 回调通路
curl -X POST http://localhost:7500/api/v1/callback/test \
  -H "X-Callback-URL: http://mailmindhub:8080/api/harness/callback"
```

### 2. 环境变量配置

```bash
# harness 侧
export HARNESS_API_TOKEN="your-secret-token"          # 可选，开发模式可为空
export HARNESS_DB_PATH="webui/harness.db"

# MailMindHub 侧
export HARNESS_API_URL="http://localhost:7500"
export HARNESS_API_TOKEN="your-secret-token"           # 需与 harness 侧一致
export MAILMINDHUB_CALLBACK_URL="http://mailmindhub:8080/api/harness/callback"
```

### 3. 确认可用 Agent

```bash
curl http://localhost:7500/api/v1/agents | python3 -m json.tool
```

确认输出中有活跃的 agent（planner / generator / evaluator 角色至少各有一个）。

---

## 测试场景总览

| 编号 | 场景 | 邮件命令 | 预期 Pipeline | 预计耗时 |
|------|------|----------|---------------|----------|
| T1 | 代码生成（泛型排序） | `/generate` | code_generation | 2-5 min |
| T2 | 代码审查（安全审计） | `/review` | code_review | 2-5 min |
| T3 | Bug 修复 | `/fix` | bug_fix | 2-5 min |
| T4 | 无法识别的命令 | 任意未知文本 | 无（返回帮助） | < 10 sec |
| T5 | 通用 API 创建任务 | 不通过邮件 | 自定义 | 2-5 min |
| T6 | Webhook 回调测试 | — | — | < 30 sec |

---

## 测试用例详解

### T1: 代码生成 — 泛型快速排序

**目的**: 验证 `/generate` 路由规则 + code_generation Pipeline 完整流程

**发送邮件**:
```
收件人: your-mailmindhub@example.com
主题: /generate 写一个泛型快速排序函数

正文:
/generate 写一个泛型快速排序函数

要求：
1. 支持泛型（Python typing.Generic 或 TypeScript 泛型）
2. 包含单元测试
3. 代码风格符合 PEP 8
4. 处理边缘情况（空列表、已排序列表）
```

**预期流程**:
```
MailMindHub 收到邮件
    ↓
POST /api/v1/tasks/from-email
    ↓
harness 匹配路由规则: ^(generate|/generate|/gen|/g)\s+(.+)
    ↓
创建 Pipeline 任务 (pipeline=code_generation)
    ↓
立即返回: {"task_id": 1, "status": "pending"}
    ↓
harness 后台执行:
  [1] Planner (Claude) → 生成 plan.md
  [2] Generator (Qwen) → 实现代码 + 测试
  [3] Evaluator (Claude) → 审查代码 → VERDICT: PASS
    ↓
Webhook 回调 → MailMindHub
    ↓
MailMindHub 回复用户邮件
```

**验证点**:

1. **任务创建成功**（立即返回，不等执行）:
```bash
# MailMindHub 日志应显示:
✅ Email task created: id=1, subject=/generate 写一个泛型快速排序函数
```

2. **Pipeline 执行完整**（通过 WebUI 或 API 查看）:
```bash
curl http://localhost:7500/api/v1/tasks/1 | python3 -m json.tool
```
预期输出 `runs` 数组包含 3 个步骤（planning / generating / evaluating），且 `eval_verdict: "PASS"`。

3. **Webhook 回调送达**:
```bash
# MailMindHub 日志应显示:
📨 Harness callback: task=1, status=completed, title=[email] 写一个泛型快速排序函数
📧 Email ready: subject='[harness] Task #1 ✅'
```

4. **用户收到回复邮件**:
```
主题: [harness] Task #1 ✅
正文: 包含 ✅ 任务完成、执行步骤、最终代码等
```

---

### T2: 代码审查 — 安全审计

**目的**: 验证 `/review` 路由规则 + code_review Pipeline

**发送邮件**:
```
收件人: your-mailmindhub@example.com
主题: /review 审查以下认证代码的安全性

正文:
/review 请审查以下代码的安全性问题：

```python
def login(username, password):
    user = db.query(f"SELECT * FROM users WHERE username='{username}'")
    if user and user.password == password:
        return True
    return False
```

重点检查 SQL 注入和密码存储安全问题。
```

**预期流程**:
```
harness 匹配路由: ^(review|/review)\s+(.+)
    ↓
Pipeline: code_review
    ↓
执行:
  [1] Planner → 制定审查计划
  [2] Generator → 分析代码，指出问题
  [3] Evaluator → 最终评审 → VERDICT: FAIL (发现安全问题)
    ↓
（可选）Generator 尝试修复 → 重新评估
    ↓
Webhook 回调 → MailMindHub → 用户收到审查报告
```

**预期回复邮件内容**:
```
主题: [harness] Task #2 ✅
正文:
✅ 任务完成

任务: 审查以下认证代码的安全性
耗时: 180秒
状态: ✅ Success

执行步骤:
✅ planning (Claude Planner)
✅ generating (Qwen Generator)
✅ evaluating (Claude Evaluator)

发现的问题:
1. SQL 注入漏洞 — 使用字符串拼接构建 SQL 查询
2. 密码明文比对 — 应使用 bcrypt 哈希
3. 无速率限制 — 可能遭受暴力破解攻击
```

---

### T3: Bug 修复

**目的**: 验证 `/fix` 路由规则 + bug_fix Pipeline

**发送邮件**:
```
收件人: your-mailmindhub@example.com
主题: /fix 修复登录页面的空指针异常

正文:
/fix 以下代码在用户名为空时会抛出 NullPointerException：

```python
def validate_login(request):
    username = request.form['username']
    if len(username) < 3:
        return "用户名至少3个字符"
    return None
```

请修复并添加完整的输入验证。
```

**预期流程**:
```
harness 匹配路由: ^(fix|/fix)\s+(.+)
    ↓
Pipeline: bug_fix
    ↓
执行:
  [1] Planner → 分析 Bug 根因
  [2] Generator → 修复代码 + 添加验证
  [3] Evaluator → 验证修复 → VERDICT: PASS
    ↓
Webhook 回调 → 用户收到修复后的代码
```

---

### T4: 无法识别的命令

**目的**: 验证路由规则匹配失败时的帮助信息返回

**发送邮件**:
```
收件人: your-mailmindhub@example.com
主题: 今天天气怎么样？

正文:
你好，请问今天天气怎么样？帮我查一下。
```

**预期流程**:
```
harness 尝试匹配路由 → 无匹配规则
    ↓
返回: {"status": "unknown_command", "help_sent": true}
    ↓
MailMindHub 生成帮助信息回复用户
```

**预期回复邮件**:
```
主题: [harness] 无法识别的命令
正文:
🤖 harness - AI Agent Orchestrator

可用命令：

📝 代码生成：
  /generate <描述>  或  /gen <描述>
  示例：/generate 写一个快速排序函数

🔍 代码审查：
  /review <描述>
  示例：/review 审查src/auth.py的安全性

🐛 Bug修复：
  /fix <描述>
  示例：/fix 修复登录页面的空指针异常

💡 帮助：
  /help  或  ?  显示此帮助信息
```

---

### T5: 通用 API 创建任务（不通过邮件）

**目的**: 验证直接调用 API 创建任务的流程

**测试命令**:
```bash
curl -X POST http://localhost:7500/api/v1/tasks \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-token" \
  -d '{
    "title": "API 测试任务",
    "prompt": "写一个 Python 函数，实现 FizzBuzz",
    "success_criteria": "1. 1-100 的数字\n2. 3的倍数输出Fizz\n3. 5的倍数输出Buzz\n4. 15的倍数输出FizzBuzz",
    "pipeline_mode": true,
    "callback_url": "http://mailmindhub:8080/api/harness/callback",
    "source": "api",
    "metadata": {
      "test_case": "T5",
      "initiated_by": "manual-curl"
    }
  }'
```

**预期响应**:
```json
{
  "task_id": 5,
  "status": "pending",
  "message": "任务已创建，正在后台执行"
}
```

**轮询检查状态**（可选，用于调试）:
```bash
# 每隔 10 秒检查一次
watch -n 10 'curl -s http://localhost:7500/api/v1/tasks/5 | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Status: {d[\"status\"]}\")"'
```

**完成后验证**:
```bash
curl http://localhost:7500/api/v1/tasks/5 | python3 -m json.tool
```

检查 `status: "completed"` 且 `runs` 包含完整的 Pipeline 步骤。

---

### T6: Webhook 回调端点测试

**目的**: 验证 MailMindHub 的回调接收端点是否正常工作

**测试命令**:
```bash
curl -X POST http://localhost:7500/api/v1/callback/test \
  -H "X-API-Key: your-secret-token" \
  -H "X-Callback-URL: http://mailmindhub:8080/api/harness/callback"
```

**预期响应**:
```json
{
  "status": "ok",
  "response_code": 200,
  "url": "http://mailmindhub:8080/api/harness/callback"
}
```

**MailMindHub 侧验证**:
```bash
# 检查 MailMindHub 日志
journalctl -u mailmindhub -f | grep "Harness callback"
# 应显示:
# 📨 Harness callback: task=0, status=completed, title=Test Callback
```

---

## 批量测试脚本

将以下脚本保存为 `scripts/test-email-integration.sh` 用于批量测试：

```bash
#!/bin/bash
# MailMindHub × harness 联动批量测试

set -e

HARNESS_URL="${HARNESS_API_URL:-http://localhost:7500}"
API_TOKEN="${HARNESS_API_TOKEN:-}"
CALLBACK_URL="${MAILMINDHUB_CALLBACK_URL:-http://mailmindhub:8080/api/harness/callback}"

CURL_ARGS="-s"
if [ -n "$API_TOKEN" ]; then
    CURL_ARGS="$CURL_ARGS -H X-API-Key: $API_TOKEN"
fi

echo "🧪 MailMindHub × harness 联动测试"
echo "harness URL: $HARNESS_URL"
echo "Callback URL: $CALLBACK_URL"
echo ""

# 0. 健康检查
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 0: 健康检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
HEALTH=$(curl -s $HARNESS_URL/api/v1/health)
echo "$HEALTH" | python3 -m json.tool
echo ""

# 1. 测试 Webhook 回调
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Webhook 回调测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -s -X POST $HARNESS_URL/api/v1/callback/test \
    ${API_TOKEN:+-H "X-API-Key: $API_TOKEN"} \
    -H "X-Callback-URL: $CALLBACK_URL" | python3 -m json.tool
echo ""

# 2. 查询可用 Agent
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: 查询可用 Agent"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -s $HARNESS_URL/api/v1/agents \
    ${API_TOKEN:+-H "X-API-Key: $API_TOKEN"} | python3 -m json.tool
echo ""

# 3. 创建代码生成任务
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: 创建代码生成任务"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TASK1=$(curl -s -X POST $HARNESS_URL/api/v1/tasks/from-email \
    ${API_TOKEN:+-H "X-API-Key: $API_TOKEN"} \
    -H "Content-Type: application/json" \
    -d "{
        \"subject\": \"/generate 写一个 FizzBuzz 函数\",
        \"body\": \"/generate 写一个 Python FizzBuzz 函数，包含单元测试\",
        \"from_addr\": \"test@example.com\",
        \"callback_url\": \"$CALLBACK_URL\"
    }")
echo "$TASK1" | python3 -m json.tool
TASK1_ID=$(echo "$TASK1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))")
echo ""

# 4. 创建代码审查任务
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: 创建代码审查任务"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TASK2=$(curl -s -X POST $HARNESS_URL/api/v1/tasks/from-email \
    ${API_TOKEN:+-H "X-API-Key: $API_TOKEN"} \
    -H "Content-Type: application/json" \
    -d "{
        \"subject\": \"/review 审查以下代码\",
        \"body\": \"/review 请审查这段代码的安全性：\ndef login(u, p):\n    return db.query(f\\\"SELECT * FROM users WHERE user='{u}' AND pass='{p}'\\\")\",
        \"from_addr\": \"test@example.com\",
        \"callback_url\": \"$CALLBACK_URL\"
    }")
echo "$TASK2" | python3 -m json.tool
TASK2_ID=$(echo "$TASK2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))")
echo ""

# 5. 创建无法识别的命令
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5: 无法识别的命令"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TASK3=$(curl -s -X POST $HARNESS_URL/api/v1/tasks/from-email \
    ${API_TOKEN:+-H "X-API-Key: $API_TOKEN"} \
    -H "Content-Type: application/json" \
    -d "{
        \"subject\": \"今天天气怎么样？\",
        \"body\": \"你好，请问今天天气怎么样？\",
        \"from_addr\": \"test@example.com\",
        \"callback_url\": \"$CALLBACK_URL\"
    }")
echo "$TASK3" | python3 -m json.tool
echo ""

# 6. 等待并检查结果
if [ -n "$TASK1_ID" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Step 6: 等待任务完成（最多 5 分钟）"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    MAX_WAIT=300
    INTERVAL=10
    ELAPSED=0

    while [ $ELAPSED -lt $MAX_WAIT ]; do
        STATUS=$(curl -s $HARNESS_URL/api/v1/tasks/$TASK1_ID | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
        echo "  [${ELAPSED}s] Task $TASK1_ID status: $STATUS"

        if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
            echo ""
            echo "✅ 任务完成！最终结果："
            curl -s $HARNESS_URL/api/v1/tasks/$TASK1_ID | python3 -m json.tool
            break
        fi

        sleep $INTERVAL
        ELAPSED=$((ELAPSED + INTERVAL))
    done

    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "⏰ 超时！任务仍在运行中..."
    fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 所有任务列表"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -s $HARNESS_URL/api/v1/tasks?limit=10 \
    ${API_TOKEN:+-H "X-API-Key: $API_TOKEN"} | python3 -m json.tool

echo ""
echo "✅ 测试完成！"
```

**使用方法**:
```bash
chmod +x scripts/test-email-integration.sh

# 使用默认配置
./scripts/test-email-integration.sh

# 自定义配置
HARNESS_API_URL=http://localhost:7500 \
HARNESS_API_TOKEN=my-secret \
MAILMINDHUB_CALLBACK_URL=http://localhost:8080/api/harness/callback \
./scripts/test-email-integration.sh
```

---

## 调试与排障

### 查看 harness API 日志

```bash
# 如果作为独立服务运行
journalctl -u harness-api -f

# 或查看 uvicorn 输出
uvicorn harness_api:app --host 0.0.0.0 --port 7500 --reload
```

### 查看 MailMindHub 日志

```bash
journalctl -u mailmindhub -f
# 或
tail -f /var/log/mailmindhub.log
```

### 常见错误排查

| 错误现象 | 可能原因 | 解决方案 |
|---------|---------|---------|
| `Connection refused` | harness 未启动 | `uvicorn harness_api:app --port 7500` |
| `401 Unauthorized` | API Token 不匹配 | 确认两端 `HARNESS_API_TOKEN` 一致 |
| `No routing rule matched` | 邮件格式不对 | 确保正文以 `/generate`、`/review`、`/fix` 开头 |
| `Webhook callback failed` | MailMindHub 回调端点未运行 | 检查 MailMindHub 是否正确部署 |
| Task 一直是 `pending` | 执行器未启动 | 检查 WebUI 或 executor 服务 |
| `eval_verdict: FAIL` | 代码质量未达标 | 查看 run 日志中的具体问题 |

### 手动测试路由规则匹配

```python
# 本地测试 MailGateway 的路由匹配逻辑
python3 -c "
from core.gateway.mail import MailGateway
gw = MailGateway()

# 测试生成命令
result = gw.parse_email_to_task(
    subject='/generate 写一个排序函数',
    body='/generate 写一个 Python 快速排序函数',
    from_addr='test@example.com'
)
print('Generate rule matched:', result['pipeline'] if result else 'None')

# 测试审查命令
result = gw.parse_email_to_task(
    subject='/review 代码审查',
    body='/review 请审查以下代码...',
    from_addr='test@example.com'
)
print('Review rule matched:', result['pipeline'] if result else 'None')

# 测试帮助命令
rule = gw.match_routing_rule(subject='help', body='help me')
print('Help rule matched:', rule.action if rule else 'None')

# 测试未知命令
rule = gw.match_routing_rule(subject='你好', body='今天天气怎么样？')
print('Unknown command:', 'No rule matched' if not rule else rule.action)
"
```

### 检查数据库中的任务记录

```bash
sqlite3 webui/harness.db << 'EOF'
.headers on
.mode column

-- 查看所有任务
SELECT id, title, status, source, created_at FROM tasks ORDER BY id DESC LIMIT 10;

-- 查看特定任务的执行记录
SELECT r.id, r.phase, r.status, r.agent_id, a.name as agent, r.attempt, r.eval_verdict
FROM runs r
LEFT JOIN agents a ON r.agent_id = a.id
WHERE r.task_id = 1
ORDER BY r.started_at;

-- 查看任务元数据（含回调 URL）
SELECT id, title, metadata FROM tasks WHERE source = 'email' ORDER BY id DESC LIMIT 5;
EOF
```

---

## 测试检查清单

在完成所有测试后，确认以下项目：

- [ ] harness API 健康检查通过 (`/api/v1/health`)
- [ ] Webhook 回调测试通过 (`/api/v1/callback/test`)
- [ ] `/generate` 命令能创建 code_generation 任务
- [ ] `/review` 命令能创建 code_review 任务
- [ ] `/fix` 命令能创建 bug_fix 任务
- [ ] 未知命令返回帮助信息 (`help_sent: true`)
- [ ] 任务创建后立即返回 (`task_id`, `status: pending`)
- [ ] Pipeline 执行完成（planning → generating → evaluating）
- [ ] Evaluator  verdict 为 `PASS` 或记录 `FAIL` 原因
- [ ] Webhook 回调成功送达 MailMindHub
- [ ] MailMindHub 成功回复用户邮件
- [ ] 数据库中任务状态为 `completed` 或 `failed`（非 `pending`/`running`）
- [ ] 所有 run 记录都有日志和 agent 信息

---

## 进阶测试场景

### 多轮对话测试

harness 支持通过邮件回复继续对话。测试方法：

1. 发送 `/generate` 邮件创建任务
2. 等待完成回复
3. 回复完成邮件，添加新要求（如："请再添加集成测试"）
4. 验证 MailMindHub 能创建新任务并关联上下文

### 并发任务测试

```bash
# 同时创建多个任务，验证并发执行
for i in {1..5}; do
    curl -s -X POST http://localhost:7500/api/v1/tasks/from-email \
        -H "Content-Type: application/json" \
        -d "{
            \"subject\": \"/generate 任务 $i\",
            \"body\": \"/generate 写一个计算斐波那契数列的 Python 函数（版本 $i）\",
            \"from_addr\": \"test@example.com\",
            \"callback_url\": \"http://mailmindhub:8080/api/harness/callback\"
        }" &
done
wait

# 查看所有任务
curl http://localhost:7500/api/v1/tasks?limit=10 | python3 -m json.tool
```

### 带项目路径的任务

```bash
# 创建任务并指定工作目录
curl -X POST http://localhost:7500/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "项目内代码生成",
    "prompt": "在 todo-app/ 目录下添加用户认证功能",
    "project_id": 1,
    "callback_url": "http://mailmindhub:8080/api/harness/callback"
  }'
```

---

*文档版本: 1.0 | 最后更新: 2026-04-12*
