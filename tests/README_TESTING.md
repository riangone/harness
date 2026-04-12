# MailMindHub ↔ harness 联动测试指南

> 最后更新: 2026-04-12

---

## 📋 测试环境准备

### 1. 启动 harness API

```bash
cd /home/ubuntu/ws/harness
python3 harness_api.py &
```

服务将在 `http://localhost:7500` 启动。

### 2. 验证服务

```bash
curl http://localhost:7500/api/v1/health
```

应返回：
```json
{"status": "ok", "service": "harness", "version": "2.0.0"}
```

---

## 🧪 测试文件

### 快速测试（推荐）

```bash
python3 tests/test_quick_integration.py
```

**测试内容**:
- ✅ 健康检查
- ✅ 邮件任务创建
- ✅ 任务状态查询

**运行时间**: ~10 秒

---

### 完整测试

```bash
python3 tests/test_mailmindhub_integration.py
```

**测试内容**:
1. 健康检查
2. Agent 列表查询
3. 无效邮件处理
4. 邮件任务创建（有效命令）
5. 任务状态查询
6. 任务轮询完成（最长 60 秒）
7. 通用任务创建
8. 任务列表查询

**运行时间**: ~70 秒

---

### 手动测试

#### 1. 从邮件创建任务

```bash
curl -X POST http://localhost:7500/api/v1/tasks/from-email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "/generate 写一个快速排序函数",
    "body": "/generate 请用 Python 实现一个快速排序函数，要求支持泛型类型",
    "from_addr": "test@example.com"
  }'
```

**响应**:
```json
{
  "task_id": 14,
  "status": "pending",
  "message": "任务已创建，Pipeline: code_generation"
}
```

#### 2. 查询任务状态

```bash
curl http://localhost:7500/api/v1/tasks/14
```

#### 3. 查询任务列表

```bash
curl http://localhost:7500/api/v1/tasks?limit=10
```

---

## 📊 支持的邮件命令

| 命令 | 示例 | Pipeline |
|------|------|----------|
| `/generate` 或 `/gen` 或 `/g` | `/generate 写个排序函数` | code_generation |
| `/review` | `/review 审查代码安全性` | code_review |
| `/fix` | `/fix 修复空指针异常` | bug_fix |
| `/help` 或 `?` | `/help` | 返回帮助信息 |

---

## 🔄 完整调用流程

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
                      harness API
                      POST /api/v1/tasks/from-email
                      │ 立即返回 task_id
                      │
                      Pipeline执行（后台异步）
                      (planner → generator → evaluator)
                      │
                      Webhook 回调通知
                      POST {callback_url}
                      {
                        "task_id": 14,
                        "status": "completed",
                        "email_content": {
                          "subject": "[harness] Task #14 ✅",
                          "body": "✅ 任务完成..."
                        }
                      }
                      │
                      ▼
                   MailMindHub
                   回复用户邮件
```

---

## ✅ 测试通过标准

| 测试项 | 通过标准 |
|--------|---------|
| 健康检查 | 返回 `{"status": "ok"}` |
| 邮件任务创建 | 返回 task_id 和 Pipeline 名称 |
| 无效命令处理 | 返回 `{"help_sent": true}` |
| 任务状态查询 | 返回任务详细信息和执行步骤 |
| 任务列表查询 | 返回任务列表和总数 |

---

## 🐛 常见问题

### 1. harness API 无法启动

**错误**: `Connection refused`

**解决**:
```bash
# 检查端口占用
lsof -i :7500

# 启动服务
cd /home/ubuntu/ws/harness && python3 harness_api.py &
```

### 2. 任务一直处于 pending 状态

**原因**: 后台执行器未配置或 AI 模型 CLI 不可用

**检查**:
```bash
# 查看任务详情
curl http://localhost:7500/api/v1/tasks/{task_id}

# 检查 runs 字段是否有执行记录
```

### 3. 邮件命令无法识别

**检查**: `config/gateway.yaml` 中的路由规则

```yaml
mail:
  routing_rules:
    - pattern: "^(generate|/generate|/gen|/g)\\s+(.+)"
      action: create_task
      pipeline: code_generation
```

---

## 📚 相关文档

- [测试报告](TEST_REPORT.md) - 详细测试结果
- [API 协议文档](../docs/API_PROTOCOL.md) - 完整 API 规范
- [架构设计](../DESIGN_V2.md) - 系统设计文档
- [MailMindHub 集成](../integrations/mailmindhub/harness_backend.py) - 客户端代码

---

*最后测试: 2026-04-12 - ✅ 联动测试通过*
