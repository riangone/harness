# Harness 2.0 — 架构升级设计文档

> 基于《借鉴HermesAgent的改进建议.md》+ 架构决策分析 + 三大核心仓库调研
> 
> 创建日期: 2026-04-12
> 状态: **待实施**

---

## 🎯 战略定位

```yaml
核心定位: "AI Agent Orchestrator — 多模型协作编排内核 + HTTP API 服务"

差异化价值:
  ✅ 多模型协作（非单一大脑）
  ✅ HTTP API 异步入口（非即时聊天）
  ✅ 配置驱动编排（非硬编码流程）
  ✅ 轻量可演进（非重型框架）

关键原则:
  - 不做"轻量版 Hermes"，做"Hermes + Airflow + CLI Agent"的融合体
  - API 优先：以 HTTP API 为主入口，WebUI 为管理界面
  - 渐进式演进：先抽象层 → 再记忆/模板 → 最后自动化优化
  - 保持轻量：默认本地存储（SQLite），支持后续切换向量库
  - 配置驱动：所有策略通过 YAML 定义，零代码修改适配新场景

架构决策:
  - harness 不包含 SMTP/IMAP，邮件收发由 MailMindHub 独占
  - harness 是纯编排内核，通过 FastAPI 提供 HTTP API
  - CLI 不适合长任务，HTTP API（提交即返回）是正确模式
  - Webhook 回调优于轮询（创建任务时传入 callback_url）
```

---

## 📊 三大参考仓库本质定位

| 项目 | 本质 | 核心能力 | harness 借鉴点 |
|------|------|----------|---------------|
| **Hermes Agent** | 单Agent自进化系统 | 技能/记忆/自我优化/多平台 | 技能系统思路、记忆机制、上下文管理 |
| **MailMindHub** | 邮件驱动任务入口 | 异步交互/自然语言解析/定时调度 | 邮件gateway集成、任务转换逻辑 |
| **harness (现有)** | 多模型Pipeline编排 | 角色分工/反馈循环/WebUI | **核心保持不变，增强抽象层和智能化** |

### 关键洞察

```
❌ Hermes = "一个大脑"（单Agent自我进化）
✅ harness = "多个大脑的调度系统"（多Agent协作编排）

📬 MailMindHub = "输入输出层"（邮件异步网关）
🧠 harness = "调度层"（编排引擎 + HTTP API）
🤖 各种CLI = "Worker"（执行单元）
```

---

## 🏗️ 目标架构

### 修正后的架构（2026-04-12）

```
            ┌──────────────────┐
            │   MailMindHub    │  ← 邮件入口（主入口）
            │  (现有，保留)     │
            └────────┬─────────┘
                     │ HTTP API
            ┌────────▼─────────┐
            │   harness API    │  ← FastAPI HTTP 服务
            │   Orchestrator   │     - POST /api/v1/tasks
            └────────┬─────────┘     - POST /api/v1/tasks/from-email
                     │               - Webhook 回调通知
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
 Claude CLI      Qwen CLI       Codex CLI
(planner)    (generator)      (generator)
```

### 调用流程

```
 1 用户 ──邮件──→ MailMindHub
 2                    │
 3             判断任务类型
 4                    │
 5         ┌──────────┴──────────┐
 6         │                     │
 7    简单对话             复杂Pipeline任务
 8    (MailMindHub             │
 9     自己AI处理)              │
10                              ▼
11                     harness API (HTTP)
12                     POST /api/v1/tasks/from-email
13                     │ 立即返回 task_id
14                     │
15                     Pipeline执行（后台异步）
16                     (多模型协作)
17                     │
18                     回调通知结果
19                     POST {callback_url}
20                     {
21                       "task_id": 42,
22                       "status": "completed",
23                       "email_content": {
24                         "subject": "[harness] Task #42 ✅",
25                         "body": "✅ 任务完成..."
26                       }
27                     }
28                     │
29                              ▼
30                     MailMindHub
                        回复用户邮件
```

### 模块结构

```
harness/
├── core/                      # 核心编排引擎（新增）
│   ├── orchestrator.py        # 主控制器
│   ├── models/
│   │   ├── registry.py        # 模型抽象层
│   │   └── provider.py        # 模型提供商接口
│   ├── memory/
│   │   ├── service.py         # 记忆服务
│   │   └── compressor.py      # 上下文压缩
│   ├── pipeline/
│   │   ├── engine.py          # Pipeline执行引擎
│   │   └── template.py        # 模板加载/匹配
│   └── gateway/
│       ├── mail.py            # 邮件解析（仅解析，不收发）
│       └── __init__.py
│
├── config/                    # 配置文件（新增）
│   ├── models.yaml            # 模型配置
│   ├── memory.yaml            # 记忆配置
│   └── gateway.yaml           # 邮件解析配置（无SMTP）
│
├── templates/                 # Pipeline模板（新增）
│   ├── code_generation.yaml
│   ├── code_review.yaml
│   └── bug_fix.yaml
│
├── harness_api.py             # ⭐ 独立 API Server（可独立启动）
│
├── webui/                     # 现有WebUI（保留+增强）
│   ├── app/
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── routers/
│   │   │   └── external_api.py  # ⭐ 增强版 API（Webhook 支持）
│   │   ├── services/
│   │   │   └── executor.py    # 现有执行器（保留兼容）
│   │   └── ...
│   └── ...
│
├── integrations/
│   └── mailmindhub/
│       └── harness_backend.py  # ⭐ MailMindHub 侧客户端（Webhook 支持）
│
├── docs/
│   └── API_PROTOCOL.md        # ⭐ API 协议文档
│
├── data/                      # 运行时数据（.gitignore）
│   ├── harness.db             # 现有数据库
│   └── memory.db              # 记忆数据库
│
├── tasks/                     # 现有任务目录（保留）
├── scripts/                   # 脚本目录（保留）
├── DESIGN.md                  # 原始设计（保留）
├── DESIGN_V2.md               # 本文档
└── AGENTS.md                  # 代理指南（更新）
```

---

## 🔧 核心模块设计

### 1️⃣ 模型抽象层 `core/models/registry.py`

#### 配置文件 `config/models.yaml`

```yaml
providers:
  openrouter:
    api_key_env: OPENROUTER_KEY
    base_url: https://openrouter.ai/api/v1
    models:
      - id: qwen/qwen-2.5-coder-32b
        roles: [generator, bug_fixer]
        cost_per_1k: 0.002
        context_window: 32768
        quality_score: 0.85

      - id: anthropic/claude-3-5-sonnet
        roles: [planner, evaluator, architect]
        cost_per_1k: 0.015
        context_window: 200000
        quality_score: 0.98

  local:
    base_url: http://localhost:11434/v1
    models:
      - id: qwen2.5-coder:7b
        roles: [generator, quick_fix]
        cost_per_1k: 0.0
        requires_gpu: true

routing:
  default_strategy: cost_aware  # cost_aware | quality_first | balanced
  
  fallback_chain:
    - try: [claude-3-5-sonnet, qwen-2.5-coder]
    - fallback: [gemini-2.0-flash]
    - emergency: [qwen2.5-coder:7b]  # local fallback

  budget_rules:
    - role: generator
      max_cost_per_task: 0.5
      auto_switch_when: 0.8  # 消耗80%预算时切廉价模型
```

#### 核心接口

```python
# core/models/registry.py
from dataclasses import dataclass
from typing import Optional, List, Dict
import yaml
import os

@dataclass
class ModelSpec:
    id: str
    roles: List[str]
    cost_per_1k: float
    quality_score: float
    context_window: int
    provider: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None

class ModelRegistry:
    def __init__(self, config_path: str = "config/models.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self._models = self._parse_models()
        self._availability_cache: Dict[str, bool] = {}

    def select(self, role: str, context: dict = None) -> ModelSpec:
        """智能选择模型：支持角色偏好 + 成本约束 + 质量权衡"""
        context = context or {}
        strategy = context.get('strategy', self.config.get('routing', {}).get('default_strategy', 'balanced'))
        
        candidates = self._filter_by_role(role)
        if not candidates:
            raise ValueError(f"No models found for role: {role}")

        # 按策略排序
        if strategy == 'cost_aware':
            candidates.sort(key=lambda m: m.cost_per_1k)
        elif strategy == 'quality_first':
            candidates.sort(key=lambda m: m.quality_score, reverse=True)
        else:  # balanced
            candidates.sort(key=lambda m: m.quality_score / max(m.cost_per_1k, 0.001), reverse=True)

        # 预算过滤
        if context.get('budget'):
            candidates = [m for m in candidates if m.cost_per_1k <= context['budget']]
            if not candidates:
                candidates = self._filter_by_role(role)  # 重置

        # 按可用性检查
        for model in candidates:
            if self._check_availability(model):
                return model

        # fallback链
        return self._try_fallback(role)

    def _filter_by_role(self, role: str) -> List[ModelSpec]:
        models = []
        for provider_name, provider_cfg in self.config.get('providers', {}).items():
            for model_cfg in provider_cfg.get('models', []):
                if role in model_cfg.get('roles', []):
                    model = ModelSpec(
                        id=model_cfg['id'],
                        roles=model_cfg['roles'],
                        cost_per_1k=model_cfg.get('cost_per_1k', 0),
                        quality_score=model_cfg.get('quality_score', 0.5),
                        context_window=model_cfg.get('context_window', 4096),
                        provider=provider_name,
                        base_url=provider_cfg.get('base_url'),
                        api_key=os.environ.get(provider_cfg.get('api_key_env', ''))
                    )
                    models.append(model)
        return models

    def _check_availability(self, model: ModelSpec) -> bool:
        if model.id in self._availability_cache:
            return self._availability_cache[model.id]
        
        # 简单检查：API key是否存在
        available = bool(model.api_key) if model.api_key is not None else True
        self._availability_cache[model.id] = available
        return available

    def _try_fallback(self, role: str) -> ModelSpec:
        """尝试fallback链"""
        fallback_chain = self.config.get('routing', {}).get('fallback_chain', [])
        for stage in fallback_chain:
            for model_id in stage.get('try', []):
                for model in self._filter_by_role(role):
                    if model.id == model_id and self._check_availability(model):
                        return model
        # 最后返回任意可用模型
        candidates = self._filter_by_role(role)
        if candidates:
            return candidates[0]
        raise ValueError(f"No available models for role: {role}")
```

**收益**:
- ✅ 新增模型零代码修改
- ✅ 成本/质量动态平衡
- ✅ 自动熔断 fallback

---

### 2️⃣ 轻量记忆系统 `core/memory/service.py`

#### 配置文件 `config/memory.yaml`

```yaml
memory:
  store: sqlite
  database: data/memory.db

  short_term:
    max_tokens: 8000
    compression:
      enabled: true
      trigger_ratio: 0.8
      model_strategy: cost_aware  # 用低成本模型做压缩

  long_term:
    index_fields: [task_type, agent_role, outcome, tags]
    retention_days: 90
    similarity_threshold: 0.7

  learning:
    enabled: true
    patterns:
      - trigger: task_failed
        action: extract_lesson
        store_as: failure_pattern
      - trigger: task_succeeded
        action: extract_workflow
        store_as: success_template
```

#### 核心接口

```python
# core/memory/service.py
import sqlite3
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

class MemoryService:
    def __init__(self, config_path: str = "config/memory.yaml"):
        import yaml
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        
        self.db_path = self.config['memory']['database']
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT,
                    agent_role TEXT,
                    outcome TEXT,  -- success / failed
                    template TEXT,  -- 成功时的模板
                    lesson TEXT,    -- 失败时的教训
                    patterns TEXT,  -- JSON: 避免的模式
                    metrics TEXT,   -- JSON: 执行指标
                    tags TEXT,      -- JSON: 标签列表
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_type 
                ON memories(task_type, outcome)
            """)

    def retrieve_similar(self, task_type: str, role: str = None, limit: int = 3) -> List[Dict]:
        """召回相似历史任务，用于 few-shot 注入"""
        query = """
            SELECT * FROM memories 
            WHERE task_type = ? 
              AND outcome = 'success'
              AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            ORDER BY created_at DESC
            LIMIT ?
        """
        params = [task_type, limit]
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
        
        return [dict(row) for row in rows]

    def store_experience(self, task_type: str, outcome: str, data: Dict):
        """任务完成后沉淀经验"""
        expires_at = None
        if self.config['memory']['long_term']['retention_days']:
            expires_at = datetime.now() + timedelta(
                days=self.config['memory']['long_term']['retention_days']
            )

        with sqlite3.connect(self.db_path) as conn:
            if outcome == 'success':
                conn.execute("""
                    INSERT INTO memories 
                    (task_type, outcome, template, metrics, tags, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    task_type,
                    outcome,
                    json.dumps(data.get('template', {})),
                    json.dumps(data.get('metrics', {})),
                    json.dumps(data.get('tags', [])),
                    expires_at
                ))
            else:
                conn.execute("""
                    INSERT INTO memories 
                    (task_type, outcome, lesson, patterns, tags, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    task_type,
                    outcome,
                    data.get('lesson', ''),
                    json.dumps(data.get('patterns', [])),
                    json.dumps(data.get('tags', [])),
                    expires_at
                ))

    def build_context_from_memories(self, memories: List[Dict]) -> str:
        """将历史记忆转换为可注入的上下文字符串"""
        if not memories:
            return ""
        
        context_parts = []
        for mem in memories:
            if mem['template']:
                context_parts.append(f"【成功案例】\n{mem['template']}")
            if mem['lesson']:
                context_parts.append(f"【失败教训】\n{mem['lesson']}")
        
        return "\n\n".join(context_parts)
```

**收益**:
- ✅ 同类任务越做越准
- ✅ 失败经验自动沉淀
- ✅ 长会话不丢失关键信息

---

### 3️⃣ 模板化 Pipeline 系统 `core/pipeline/`

#### 模板示例 `templates/code_review.yaml`

```yaml
name: code_review_pipeline
version: 1.0
description: 代码生成 → 自动审查 → 失败时修复

trigger:
  task_type: code_generation
  auto_apply: true

steps:
  - id: generate
    agent:
      role: generator
      model_selector: { strategy: cost_aware, budget: 0.3 }
    action: generate_code
    output: code_diff

  - id: review
    agent:
      role: evaluator
      model_selector: { strategy: quality_first }
    action: review_code
    input: { code: "{{ steps.generate.output.code_diff }}" }
    criteria: [syntax, logic, security, style]

  - id: conditional_fix
    condition: "{{ steps.review.output.issues|length > 0 }}"
    then:
      - agent:
          role: bug_fixer
          model_selector: { fallback_chain: true }
        action: fix_issues
        input:
          code: "{{ steps.generate.output.code_diff }}"
          feedback: "{{ steps.review.output.issues }}"

  - id: final_output
    action: merge_results
    output_format: html_diff

on_success:
  - store_template: true
  - notify: [email, webhook]
```

#### 核心接口

```python
# core/pipeline/template.py
import yaml
import os
from typing import Dict, List, Any, Optional
import re

class PipelineTemplate:
    def __init__(self, data: Dict):
        self.name = data['name']
        self.version = data.get('version', 1)
        self.description = data.get('description', '')
        self.steps = data.get('steps', [])
        self.trigger = data.get('trigger', {})
        self.on_success = data.get('on_success', [])

class TemplateLoader:
    def __init__(self, template_dir: str = "templates"):
        self.template_dir = template_dir
        self._templates: Dict[str, PipelineTemplate] = {}
        self._load_templates()

    def _load_templates(self):
        if not os.path.exists(self.template_dir):
            return
        
        for filename in os.listdir(self.template_dir):
            if filename.endswith('.yaml'):
                filepath = os.path.join(self.template_dir, filename)
                with open(filepath) as f:
                    data = yaml.safe_load(f)
                    template = PipelineTemplate(data)
                    self._templates[template.name] = template

    def match(self, task_type: str) -> Optional[PipelineTemplate]:
        """根据任务类型匹配模板"""
        for template in self._templates.values():
            if template.trigger.get('task_type') == task_type:
                return template
        return None

    def get_default(self) -> Optional[PipelineTemplate]:
        """获取默认模板"""
        return self._templates.get('default_pipeline')
```

```python
# core/pipeline/engine.py
from typing import Dict, Any
from .template import PipelineTemplate, TemplateLoader
from ..models.registry import ModelRegistry
from ..memory.service import MemoryService

class PipelineEngine:
    def __init__(self, registry: ModelRegistry, memory: MemoryService):
        self.registry = registry
        self.memory = memory
        self.templates = TemplateLoader()

    async def execute(self, task: Any) -> Dict:
        """执行Pipeline任务"""
        # 1. 加载/匹配模板
        template = self.templates.match(task.task_type) or self.templates.get_default()
        if not template:
            raise ValueError(f"No template found for task type: {task.task_type}")

        # 2. 注入历史经验（few-shot）
        memories = self.memory.retrieve_similar(task.task_type)
        context = self.memory.build_context_from_memories(memories)

        # 3. 按步骤执行
        step_results = {}
        for step in template.steps:
            # 评估条件
            if 'condition' in step:
                if not self._evaluate_condition(step['condition'], step_results):
                    continue

            # 选择模型
            agent_config = step.get('agent', {})
            model = self.registry.select(
                role=agent_config.get('role', 'generator'),
                context=agent_config.get('model_selector', {})
            )

            # 执行步骤
            step_results[step['id']] = await self._run_step(
                step, model, context, step_results
            )

        # 4. 沉淀经验
        self.memory.store_experience(
            task.task_type,
            'success',
            {'template': step_results, 'metrics': {}}
        )

        return step_results

    def _evaluate_condition(self, condition: str, results: Dict) -> bool:
        """评估条件表达式"""
        # 简化的条件评估（实际应使用模板引擎）
        # 示例: "{{ steps.review.output.issues|length > 0 }}"
        match = re.search(r'steps\.(\w+)\.output\.(\w+)', condition)
        if match:
            step_id, key = match.groups()
            value = results.get(step_id, {}).get(key, [])
            if 'length > 0' in condition:
                return len(value) > 0
        return True

    async def _run_step(self, step: Dict, model: Any, context: str, prev_results: Dict) -> Dict:
        """执行单个步骤"""
        # 实际实现会调用对应的CLI或API
        # 这里返回占位结果
        return {'status': 'completed', 'output': {}}
```

**收益**:
- ✅ 比Hermes Skill系统轻量10倍
- ✅ 配置驱动
- ✅ 支持条件分支/并行

---

### 4️⃣ 邮件网关集成 `core/gateway/mail.py`

#### 配置文件 `config/gateway.yaml`

```yaml
mail:
  enabled: true
  provider: mailmindhub

  mailmindhub:
    api_endpoint: http://localhost:8080/api
    auth:
      token_env: MAILMINDHUB_TOKEN

  routing_rules:
    - pattern: "^(review|/review) (.+)"
      action: create_task
      pipeline: code_review
    - pattern: "^(generate|/gen) (.+)"
      action: create_task
      pipeline: code_generation

  response_template: |
    Subject: [harness] Task #{task_id} Completed
    Content-Type: text/html

    <h3>✅ Task Completed</h3>
    <p><strong>Task:</strong> {task_summary}</p>
    <p><strong>Duration:</strong> {duration}s</p>
    
    {% if result.diff %}
    <details>
      <summary>📝 Code Changes</summary>
      <pre><code class="language-diff">{result.diff}</code></pre>
    </details>
    {% endif %}
```

#### 核心接口

```python
# core/gateway/mail.py
import os
import re
from typing import Optional, Dict, Any
from jinja2 import Template

class MailGateway:
    def __init__(self, config_path: str = "config/gateway.yaml"):
        import yaml
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        
        self.mmh_token = os.environ.get(
            self.config['mail']['mailmindhub']['auth']['token_env'],
            ''
        )
        self.api_endpoint = self.config['mail']['mailmindhub']['api_endpoint']
        self.response_template = Template(self.config['mail']['response_template'])

    def match_routing_rule(self, subject: str, body: str) -> Optional[Dict]:
        """匹配路由规则"""
        content = f"{subject}\n{body}"
        for rule in self.config['mail']['routing_rules']:
            if re.match(rule['pattern'], content, re.IGNORECASE):
                return rule
        return None

    def parse_email_to_task(self, subject: str, body: str) -> Optional[Dict]:
        """邮件 → harness task 转换"""
        rule = self.match_routing_rule(subject, body)
        if not rule:
            return None

        # 提取任务内容
        match = re.match(rule['pattern'], body, re.IGNORECASE)
        task_content = match.group(2) if match else body

        return {
            'pipeline': rule.get('pipeline', 'default'),
            'input': task_content,
            'metadata': {'source': 'email'}
        }

    def format_task_complete_response(self, task: Dict, result: Dict) -> str:
        """task 完成 → 邮件回复"""
        return self.response_template.render(
            task_id=task.get('id', 'N/A'),
            task_summary=task.get('input', '')[:100],
            duration=result.get('duration', 0),
            result=result
        )

    async def send_email(self, to: str, subject: str, content: str):
        """通过MailMindHub发送邮件"""
        import aiohttp
        
        headers = {
            'Authorization': f'Bearer {self.mmh_token}',
            'Content-Type': 'application/json'
        }
        payload = {
            'to': to,
            'subject': subject,
            'content': content
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{self.api_endpoint}/send',
                headers=headers,
                json=payload
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to send email: {resp.status}")
```

**收益**:
- ✅ 异步长任务友好
- ✅ 结构化输出
- ✅ 与现有MailMindHub无缝集成

---

### 5️⃣ 主编排器 `core/orchestrator.py`

```python
# core/orchestrator.py
import asyncio
import yaml
from .models.registry import ModelRegistry
from .memory.service import MemoryService
from .pipeline.engine import PipelineEngine
from .gateway.mail import MailGateway

class HarnessOrchestrator:
    def __init__(self, config_dir: str = "config"):
        self.registry = ModelRegistry(f"{config_dir}/models.yaml")
        self.memory = MemoryService(f"{config_dir}/memory.yaml")
        self.pipeline = PipelineEngine(self.registry, self.memory)
        self.gateway = MailGateway(f"{config_dir}/gateway.yaml")

    async def run(self):
        """主循环：监听邮件 + 执行任务"""
        print("🚀 Harness Orchestrator started")
        print("📬 Listening for emails...")
        
        # 这里应该接入MailMindHub的邮件监听
        # 简化示例：
        while True:
            # 1. 检查新邮件
            emails = await self.gateway.check_new_emails()
            
            for email in emails:
                # 2. 解析邮件内容
                task = await self.gateway.parse_email_to_task(
                    email.subject, 
                    email.body
                )
                if not task:
                    await self.gateway.send_reply(
                        email.from_addr,
                        "Unknown Command",
                        "请发送有效的指令。示例: /generate 写一个排序函数"
                    )
                    continue

                # 3. 执行Pipeline
                try:
                    result = await self.pipeline.execute(task)
                    
                    # 4. 发送完成通知
                    response = self.gateway.format_task_complete_response(
                        task, result
                    )
                    await self.gateway.send_email(
                        email.from_addr,
                        f"Task Completed",
                        response
                    )
                except Exception as e:
                    await self.gateway.send_email(
                        email.from_addr,
                        "Task Failed",
                        f"错误: {str(e)}"
                    )

            await asyncio.sleep(30)  # 30秒轮询一次
```

---

## 📋 实施路线图

| 阶段 | 周期 | 目标 | 关键交付物 | 验收标准 |
|------|------|------|-----------|----------|
| **🥇 Phase 1** | 1-2周 | 模型抽象层 + 邮件通知 | `core/models/registry.py`<br/>`config/models.yaml`<br/>邮件通知hook | 新增模型零代码修改<br/>任务完成自动发邮件 |
| **🥈 Phase 2** | 2-3周 | 模板引擎 + 轻量记忆 | `core/pipeline/`<br/>`core/memory/`<br/>`config/memory.yaml` | Pipeline可复用<br/>历史经验自动注入 |
| **🥉 Phase 3** | 3-4周 | 邮件→Task + 并行执行 | `core/gateway/mail.py`反向通道<br/>并行executor | 邮件创建任务<br/>多模型并行选优 |
| **🔜 Phase 4** | 可选 | 自动优化 + 可观测性 | 轻量技能进化<br/>trace/replay | 问题快速定位<br/>规则自动沉淀 |

---

## ⚠️ 明确不做的内容（v1范围外）

```yaml
out_of_scope_v1:
  - ❌ Hermes 完整 Skill 系统（RL/自动抽象）
  - ❌ 向量数据库 + 用户画像建模
  - ❌ Telegram/Slack 等多平台网关（邮件已足够）
  - ❌ OpenTelemetry 全链路追踪（先 print + JSON log）
  - ❌ 容器隔离/沙箱执行（先靠白名单 + 人工审核）

rationale: |
  早期核心是验证"邮件+编排"的产品价值，
  而非追求技术完备性。每增加一个"高级特性"，
  都要问：这个能让用户明天就用得更好吗？
```

---

## 🔄 与现有WebUI的兼容性

### 保留不变
- WebUI界面和路由
- 数据库结构（agents/projects/tasks/runs）
- 现有executor.py的CLI执行逻辑
- 认证和多语言系统

### 新增内容
- `core/` 目录（新模块）
- `config/` 目录（配置文件）
- `templates/` 目录（Pipeline模板）
- 邮件gateway集成

### 兼容策略
```python
# webui/app/services/executor.py 中：
# 保留现有CLI调用逻辑，新增可选的orchestrator模式

def execute_task(task, use_orchestrator=False):
    if use_orchestrator:
        # 使用新的编排引擎
        orchestrator = HarnessOrchestrator()
        return orchestrator.run_task(task)
    else:
        # 使用现有逻辑（保持向后兼容）
        return legacy_execute(task)
```

---

## 📝 数据库扩展

### 新增表：pipeline_templates

```sql
CREATE TABLE pipeline_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    version INTEGER DEFAULT 1,
    description TEXT,
    content TEXT NOT NULL,  -- YAML内容
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 新增表：task_memories

```sql
CREATE TABLE task_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    agent_role TEXT,
    outcome TEXT NOT NULL,  -- success/failed
    template TEXT,          -- 成功经验
    lesson TEXT,            -- 失败教训
    metrics TEXT,           -- JSON指标
    tags TEXT,              -- JSON标签
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE INDEX idx_memories_type ON task_memories(task_type, outcome);
```

### 扩展现有tasks表

```sql
ALTER TABLE tasks ADD COLUMN task_type TEXT;  -- 用于匹配模板
ALTER TABLE tasks ADD COLUMN template_id INTEGER REFERENCES pipeline_templates(id);
ALTER TABLE tasks ADD COLUMN source TEXT DEFAULT 'webui';  -- webui/email/cli
```

---

## 💡 关键设计决策

### 1. 为什么做模型抽象层？
**问题**: 现有代码中模型硬编码，新增需改多处
**方案**: Registry模式 + YAML配置
**收益**: 零代码修改支持新模型、成本/质量动态平衡

### 2. 为什么做轻量记忆而非向量库？
**问题**: 任务间无经验积累，重复犯错
**方案**: SQLite + 关键词匹配（先不用向量）
**收益**: 同类任务越做越准，失败经验自动沉淀

### 3. 为什么做模板化Pipeline而非Skill系统？
**问题**: Hermes Skill太重（需RL/抽象）
**方案**: YAML定义Pipeline步骤 + 条件分支
**收益**: 配置驱动、比Skill简单10倍但效果70%一样

### 4. 为什么优先邮件而非Telegram？
**问题**: 即时聊天不适合长时任务
**方案**: MailMindHub已有完整邮件系统
**收益**: 异步友好、结构化输出、企业场景适配

---

## 🎯 最终战略

```yaml
核心定位: |
  不是"更好的Hermes"
  而是"AI编排操作系统"

差异化:
  - 多模型协作（非单一大脑）
  - 邮件异步入口（非即时聊天）
  - 配置驱动编排（非硬编码流程）
  - 轻量可演进（非重型框架）

愿景: |
  当别人在卷"单智能体多聪明"时，
  我们在解决"多个智能体如何高效协作"——
  这才是企业级AI应用的真实痛点。
```

---

## 📚 参考资料

- [Hermes Agent](https://github.com/nousresearch/hermes-agent) - NousResearch自进化AI Agent
- [MailMindHub](https://github.com/riangone/mailmindhub) - 邮件驱动AI交互平台
- [借鉴HermesAgent的改进建议.md](./借鉴HermesAgent的改进建议.md) - 原始改进建议文档
- 架构决策分析记录 - 战略定位和优先级建议

---

**文档状态**: 初稿完成
**下一步**: 开始Phase 1实施（模型抽象层 + 邮件通知）
