# Harness 2.0 快速入门

> 3分钟上手指南

---

## 🚀 快速开始

### 1. 安装

```bash
pip install pyyaml jinja2 aiohttp
```

### 2. Python API

```python
from core.orchestrator import HarnessOrchestrator
import asyncio

async def main():
    orch = HarnessOrchestrator("config")
    
    # 运行任务
    result = await orch.run_task(
        task_type='code_generation',
        task_input='写一个快速排序'
    )
    
    print(f"{'成功' if result['success'] else '失败'}")
    print(f"耗时: {result['total_duration_ms']}ms")

asyncio.run(main())
```

### 3. CLI

```bash
# 查看信息
python -m core.orchestrator --action info

# 运行任务
python -m core.orchestrator --action run \
    --task-type code_generation \
    --input "写个排序函数"
```

---

## 📦 模块速查

### ModelRegistry - 模型选择

```python
from core.models import ModelRegistry

reg = ModelRegistry("config/models.yaml")

# 成本优先
model = reg.select('generator', {'strategy': 'cost_aware'})

# 质量优先
model = reg.select('planner', {'strategy': 'quality_first'})
```

### MemoryService - 记忆管理

```python
from core.memory import MemoryService

mem = MemoryService("data/memory.db")

# 存经验
mem.store_experience('code_generation', 'success', {
    'template': '用函数式风格',
    'tags': ['python']
})

# 查经验
similar = mem.retrieve_similar('code_generation', limit=3)
```

### PipelineEngine - Pipeline执行

```python
from core.pipeline import PipelineEngine
from core.models import ModelRegistry
from core.memory import MemoryService

engine = PipelineEngine(
    registry=ModelRegistry(),
    memory=MemoryService()
)

# 设置执行器（实际使用时需要实现CLI调用）
engine.set_step_executor(lambda step, model, prompt: {"status": "ok"})

# 执行
result = await engine.execute(
    task_type='code_generation',
    task_input='写个排序'
)
```

### MailGateway - 邮件网关

```python
from core.gateway import MailGateway

gw = MailGateway("config/gateway.yaml")

# 邮件→任务
task = gw.parse_email_to_task(
    subject="/gen test",
    body="/gen 写个排序",
    from_addr="user@example.com"
)

# 发送响应
await gw.send_task_response(task, result)
```

---

## 🔧 配置速查

### 添加新模型 → `config/models.yaml`

```yaml
providers:
  cli:
    models:
      - id: my_model
        roles: [generator]
        cost_per_1k: 0.003
        quality_score: 0.90
        cli_command: my-cli
```

### 创建新模板 → `templates/my_pipeline.yaml`

```yaml
name: my_pipeline
version: 1
steps:
  - id: step1
    agent:
      role: generator
      model_selector: {strategy: cost_aware}
    action: do_something
```

### 添加邮件规则 → `config/gateway.yaml`

```yaml
mail:
  routing_rules:
    - pattern: "^(mycmd)\\s+(.+)"
      action: create_task
      pipeline: my_pipeline
```

---

## 🧪 测试

```bash
python3 tests/test_core.py
```

---

## 📚 更多文档

- [完整使用指南](core/README.md)
- [架构设计](DESIGN_V2.md)
- [实施总结](IMPLEMENTATION_SUMMARY.md)
