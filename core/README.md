# Harness 2.0 核心模块使用指南

> AI Agent Orchestrator — 多模型协作编排 + 邮件驱动异步入口

---

## 📦 快速开始

### 1. 安装依赖

```bash
pip install pyyaml jinja2 aiohttp
```

### 2. 基础使用

```python
from core.orchestrator import HarnessOrchestrator
import asyncio

async def main():
    # 初始化编排器
    orchestrator = HarnessOrchestrator("config")
    
    # 运行任务
    result = await orchestrator.run_task(
        task_type='code_generation',
        task_input='写一个快速排序函数'
    )
    
    print(f"结果: {'成功' if result['success'] else '失败'}")

asyncio.run(main())
```

### 3. CLI使用

```bash
# 查看系统信息
python -m core.orchestrator --action info

# 列出可用模板
python -m core.orchestrator --action templates

# 列出可用模型
python -m core.orchestrator --action models

# 运行任务
python -m core.orchestrator --action run \
    --task-type code_generation \
    --input "写一个排序函数"
```

---

## 🏗️ 核心模块

### 1. ModelRegistry - 模型注册表

**位置**: `core/models/registry.py`

**功能**: 统一管理所有AI模型，支持智能选择和fallback

**配置**: `config/models.yaml`

```python
from core.models import ModelRegistry

registry = ModelRegistry("config/models.yaml")

# 按角色选择模型（成本优先）
model = registry.select('generator', {'strategy': 'cost_aware'})
print(f"选择: {model.id}, 成本: {model.cost_per_1k}")

# 按角色选择模型（质量优先）
model = registry.select('planner', {'strategy': 'quality_first'})

# 获取所有可用模型
all_models = registry.get_all_models()

# 获取特定角色的模型
generators = registry.get_models_for_role('generator')
```

**选择策略**:
- `cost_aware`: 成本优先（便宜优先）
- `quality_first`: 质量优先（高分优先）
- `balanced`: 平衡模式（性价比）

---

### 2. MemoryService - 记忆服务

**位置**: `core/memory/service.py`

**功能**: 管理任务经验，支持存储、检索和上下文注入

**配置**: `config/memory.yaml`

```python
from core.memory import MemoryService

memory = MemoryService("data/memory.db")

# 存储成功经验
memory.store_experience(
    task_type='code_generation',
    outcome='success',
    data={
        'template': '使用函数式编程风格',
        'metrics': {'duration': 5000},
        'tags': ['python']
    },
    agent_role='generator'
)

# 检索相似任务
similar = memory.retrieve_similar('code_generation', limit=3)

# 构建可注入的上下文
context = memory.build_context_from_memories(similar)
print(context)

# 获取统计信息
stats = memory.get_statistics()
print(f"总记忆: {stats['total']}, 成功: {stats['success']}")
```

---

### 3. PipelineEngine - Pipeline引擎

**位置**: `core/pipeline/engine.py`

**功能**: 执行模板化的Pipeline流程

**模板目录**: `templates/`

```python
from core.pipeline import PipelineEngine, TemplateLoader
from core.models import ModelRegistry
from core.memory import MemoryService

# 初始化
engine = PipelineEngine(
    registry=ModelRegistry(),
    memory=MemoryService(),
    template_dir="templates"
)

# 设置步骤执行器（需要实现实际的CLI调用）
async def my_executor(step, model, prompt):
    # 这里调用实际的CLI或API
    return {"status": "success", "output": "..."}

engine.set_step_executor(my_executor)

# 执行Pipeline
result = await engine.execute(
    task_type='code_generation',
    task_input='写一个排序函数',
    session_id='session_001'
)

print(f"模板: {result.template_name}")
print(f"成功: {result.success}")
print(f"步骤结果: {result.step_results}")
```

**可用模板**:
- `default_pipeline`: 默认单步执行
- `code_generation`: 代码生成 → 验证
- `code_review`: 代码审查 → 修复
- `bug_fix`: Bug分析 → 修复

---

### 4. MailGateway - 邮件网关

**位置**: `core/gateway/mail.py`

**功能**: 对接MailMindHub，实现邮件↔任务转换

**配置**: `config/gateway.yaml`

```python
from core.gateway import MailGateway

gateway = MailGateway("config/gateway.yaml")

# 解析邮件为任务
task = gateway.parse_email_to_task(
    subject="/generate test",
    body="/generate 写一个排序函数",
    from_addr="user@example.com"
)

if task:
    print(f"Pipeline: {task['pipeline']}")
    print(f"输入: {task['input']}")

# 发送任务完成响应
await gateway.send_task_response(
    task={'id': '123', 'from_addr': 'user@example.com'},
    result={'success': True, 'duration_ms': 5000}
)

# 获取帮助回复
help_text = gateway.generate_help_reply()
```

**支持命令**:
- `/generate` 或 `/gen`: 代码生成
- `/review`: 代码审查
- `/fix`: Bug修复
- `/help`: 帮助

---

### 5. HarnessOrchestrator - 主编排器

**位置**: `core/orchestrator.py`

**功能**: 整合所有模块，提供统一API

```python
from core.orchestrator import HarnessOrchestrator

orchestrator = HarnessOrchestrator("config")

# 运行任务
result = await orchestrator.run_task(
    task_type='code_generation',
    task_input='写一个排序函数',
    template_name='code_generation'  # 可选：指定模板
)

# 从邮件运行任务
result = await orchestrator.run_from_email(
    subject="/generate test",
    body="/generate 写一个排序函数",
    from_addr="user@example.com"
)

# 查询系统信息
info = orchestrator.get_system_info()
templates = orchestrator.list_templates()
models = orchestrator.list_models()
```

---

## 📁 目录结构

```
harness/
├── core/                      # 核心模块
│   ├── orchestrator.py        # 主编排器
│   ├── models/
│   │   └── registry.py        # 模型注册表
│   ├── memory/
│   │   ├── service.py         # 记忆服务
│   │   └── compressor.py      # 上下文压缩
│   ├── pipeline/
│   │   ├── engine.py          # Pipeline引擎
│   │   └── template.py        # 模板加载
│   └── gateway/
│       └── mail.py            # 邮件网关
│
├── config/                    # 配置文件
│   ├── models.yaml            # 模型配置
│   ├── memory.yaml            # 记忆配置
│   └── gateway.yaml           # 网关配置
│
├── templates/                 # Pipeline模板
│   ├── default.yaml
│   ├── code_generation.yaml
│   ├── code_review.yaml
│   └── bug_fix.yaml
│
├── data/                      # 运行时数据
│   └── memory.db              # 记忆数据库
│
└── tests/
    └── test_core.py           # 核心测试
```

---

## 🔧 配置指南

### 添加新模型

编辑 `config/models.yaml`:

```yaml
providers:
  cli:
    models:
      - id: new_model
        roles: [generator]
        cost_per_1k: 0.003
        quality_score: 0.90
        context_window: 8192
        cli_command: new-cli
```

### 创建新模板

在 `templates/` 目录创建YAML文件:

```yaml
name: my_custom_pipeline
version: 1
description: 自定义Pipeline

trigger:
  task_type: custom_task
  auto_apply: true

steps:
  - id: step1
    agent:
      role: generator
      model_selector:
        strategy: cost_aware
    action: do_something
    output_key: result

on_success:
  - action: store_experience
```

### 自定义邮件路由规则

编辑 `config/gateway.yaml`:

```yaml
mail:
  routing_rules:
    - pattern: "^(mycommand|/mycmd)\\s+(.+)"
      action: create_task
      pipeline: my_custom_pipeline
```

---

## 🧪 测试

运行核心模块测试:

```bash
python3 tests/test_core.py
```

测试覆盖:
- ✅ ModelRegistry: 模型选择和路由
- ✅ MemoryService: 记忆存储和检索
- ✅ MailGateway: 邮件解析和路由
- ✅ PipelineTemplate: 模板加载和匹配
- ✅ PipelineEngine: Pipeline执行
- ✅ HarnessOrchestrator: 编排器集成

---

## 📝 设计文档

详细设计请参考:
- [DESIGN_V2.md](../DESIGN_V2.md) - 架构升级设计文档
- [借鉴HermesAgent的改进建议.md](../docs/借鉴HermesAgent的改进建议.md) - 原始改进建议

---

## 🚀 下一步

Phase 1 已完成（模型抽象层 + 邮件通知）

后续计划:
- Phase 2: 集成现有WebUI executor
- Phase 3: 实现邮件监听循环
- Phase 4: 对接MailMindHub API

---

**版本**: 2.0.0-alpha
**最后更新**: 2026-04-12
