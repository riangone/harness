"""
Pipeline Template - Pipeline模板定义和加载

从YAML文件加载Pipeline模板定义，
支持条件分支、步骤编排、模型选择等。
"""

import yaml
import os
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StepAgent:
    """步骤中的代理配置"""
    role: str
    model_selector: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StepInput:
    """步骤输入配置"""
    source: str = None  # 数据来源 (task.input / steps.xxx.output)
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineStep:
    """Pipeline步骤定义"""
    id: str
    type: str = "agent"  # "agent" or "tool_call"
    agent: Optional[StepAgent] = None
    tool: Optional[str] = None
    tool_params: Dict[str, Any] = field(default_factory=dict)
    action: str = None
    input: Optional[StepInput] = None
    condition: Optional[str] = None  # 条件表达式
    output_key: str = None  # 输出存储key
    max_retries: int = 1
    timeout: int = None


@dataclass
class PipelineTrigger:
    """触发器配置"""
    task_type: str = None
    auto_apply: bool = False
    patterns: List[str] = field(default_factory=list)


@dataclass
class PipelineTemplate:
    """
    Pipeline模板
    
    定义可复用的任务编排流程
    """
    name: str
    version: int = 1
    description: str = ""
    trigger: Optional[PipelineTrigger] = None
    steps: List[PipelineStep] = field(default_factory=list)
    on_success: List[Dict] = field(default_factory=list)
    on_failure: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_step(self, step_id: str) -> Optional[PipelineStep]:
        """根据ID获取步骤"""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_step_ids(self) -> List[str]:
        """获取所有步骤ID"""
        return [step.id for step in self.steps]


class TemplateLoader:
    """
    模板加载器
    
    从templates目录加载所有YAML模板，
    支持模板匹配和查询。
    """
    
    def __init__(self, template_dir: str = "templates"):
        self.template_dir = template_dir
        self._templates: Dict[str, PipelineTemplate] = {}
        self._load_templates()

    def _load_templates(self):
        """加载所有模板文件"""
        if not os.path.exists(self.template_dir):
            logger.warning(f"Template directory not found: {self.template_dir}")
            return
        
        for filename in os.listdir(self.template_dir):
            if filename.endswith('.yaml') or filename.endswith('.yml'):
                filepath = os.path.join(self.template_dir, filename)
                try:
                    template = self._load_single(filepath)
                    if template:
                        self._templates[template.name] = template
                        logger.info(f"Loaded template: {template.name} v{template.version}")
                except Exception as e:
                    logger.error(f"Failed to load template {filepath}: {e}")

    def _load_single(self, filepath: str) -> Optional[PipelineTemplate]:
        """加载单个模板文件"""
        with open(filepath) as f:
            data = yaml.safe_load(f)
        
        if not data or 'name' not in data:
            return None

        # 解析trigger
        trigger_data = data.get('trigger', {})
        trigger = PipelineTrigger(
            task_type=trigger_data.get('task_type'),
            auto_apply=trigger_data.get('auto_apply', False),
            patterns=trigger_data.get('patterns', [])
        )

        # 解析steps
        steps = []
        for step_data in data.get('steps', []):
            agent_data = step_data.get('agent')
            agent = None
            if agent_data:
                agent = StepAgent(
                    role=agent_data.get('role', 'generator'),
                    model_selector=agent_data.get('model_selector', {})
                )

            input_data = step_data.get('input')
            step_input = None
            if input_data:
                step_input = StepInput(
                    source=input_data.get('source'),
                    data=input_data
                )

            step = PipelineStep(
                id=step_data['id'],
                type=step_data.get('type', 'agent'),
                agent=agent,
                tool=step_data.get('tool'),
                tool_params=step_data.get('tool_params', {}),
                action=step_data.get('action'),
                input=step_input,
                condition=step_data.get('condition'),
                output_key=step_data.get('output_key', step_data['id']),
                max_retries=step_data.get('max_retries', 1),
                timeout=step_data.get('timeout')
            )
            steps.append(step)

        # 处理嵌套步骤（条件分支）
        processed_steps = self._process_nested_steps(steps, data.get('steps', []))

        return PipelineTemplate(
            name=data['name'],
            version=data.get('version', 1),
            description=data.get('description', ''),
            trigger=trigger,
            steps=processed_steps,
            on_success=data.get('on_success', []),
            on_failure=data.get('on_failure', []),
            metadata={k: v for k, v in data.items() 
                     if k not in ['name', 'version', 'description', 'trigger', 'steps', 'on_success', 'on_failure']}
        )

    def _process_nested_steps(
        self,
        steps: List[PipelineStep],
        raw_steps: List[Dict]
    ) -> List[PipelineStep]:
        """处理嵌套步骤（条件分支中的then）"""
        # 简单实现：扁平化处理
        # 实际使用时可扩展支持更复杂的嵌套
        return steps

    def match(self, task_type: str) -> Optional[PipelineTemplate]:
        """
        根据任务类型匹配模板
        
        Args:
            task_type: 任务类型
            
        Returns:
            匹配的模板，如果没有则返回None
        """
        for template in self._templates.values():
            if template.trigger and template.trigger.task_type == task_type:
                return template
        return None

    def match_by_pattern(self, text: str) -> Optional[PipelineTemplate]:
        """
        根据文本模式匹配模板
        
        Args:
            text: 输入文本
            
        Returns:
            匹配的模板
        """
        import re
        
        for template in self._templates.values():
            if template.trigger and template.trigger.patterns:
                for pattern in template.trigger.patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        return template
        return None

    def get_template(self, name: str) -> Optional[PipelineTemplate]:
        """根据名称获取模板"""
        return self._templates.get(name)

    def list_templates(self) -> List[PipelineTemplate]:
        """列出所有模板"""
        return list(self._templates.values())

    def get_default(self) -> Optional[PipelineTemplate]:
        """获取默认模板"""
        return self._templates.get('default_pipeline') or self._templates.get('default')

    def reload(self):
        """重新加载所有模板"""
        self._templates.clear()
        self._load_templates()
        logger.info("Templates reloaded")
