"""
Pipeline Engine - Pipeline执行引擎

负责：
- 加载和匹配模板
- 按步骤执行Pipeline
- 条件分支评估
- 结果收集和存储
"""

import asyncio
import logging
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .template import PipelineTemplate, TemplateLoader, PipelineStep
from ..models.registry import ModelRegistry, ModelSpec
from ..memory.service import MemoryService
from ..memory.compressor import ContextCompressor

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """步骤执行结果"""
    step_id: str
    success: bool
    output: Any = None
    error: str = None
    duration_ms: int = 0
    model_used: str = None
    attempt: int = 1


@dataclass
class PipelineResult:
    """Pipeline执行结果"""
    template_name: str
    success: bool
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    total_duration_ms: int = 0
    error: str = None
    started_at: datetime = None
    completed_at: datetime = None


class PipelineEngine:
    """
    Pipeline执行引擎
    
    功能：
    - 模板匹配和加载
    - 步骤顺序/条件执行
    - 模型选择和调用
    - 结果收集和存储
    """
    
    def __init__(
        self,
        registry: ModelRegistry = None,
        memory: MemoryService = None,
        compressor: ContextCompressor = None,
        template_dir: str = "templates"
    ):
        self.registry = registry or ModelRegistry()
        self.memory = memory or MemoryService()
        self.compressor = compressor or ContextCompressor()
        self.templates = TemplateLoader(template_dir)
        
        # 执行回调（可由外部设置）
        self._step_executor = None  # async function(step, model, context) -> result

    def set_step_executor(self, executor_func):
        """
        设置步骤执行器
        
        Args:
            executor_func: async function(step, model, context) -> dict
        """
        self._step_executor = executor_func

    async def execute(
        self,
        task_type: str,
        task_input: str,
        template: PipelineTemplate = None,
        session_id: str = None,
        context: Dict[str, Any] = None
    ) -> PipelineResult:
        """
        执行Pipeline
        
        Args:
            task_type: 任务类型
            task_input: 任务输入内容
            template: 指定模板（可选，否则自动匹配）
            session_id: 会话ID
            context: 额外上下文
            
        Returns:
            PipelineResult: 执行结果
        """
        started_at = datetime.now()
        
        # 1. 加载/匹配模板
        if template is None:
            template = self.templates.match(task_type)
        if template is None:
            return PipelineResult(
                template_name="unknown",
                success=False,
                error=f"No template found for task type: {task_type}",
                started_at=started_at,
                completed_at=datetime.now()
            )

        logger.info(f"Executing pipeline: {template.name}")

        # 2. 构建初始上下文
        execution_context = self._build_context(
            task_type, task_input, session_id, context
        )

        # 3. 按步骤执行
        step_results = {}
        pipeline_success = True

        for step in template.steps:
            # 评估条件
            if step.condition:
                if not self._evaluate_condition(step.condition, step_results):
                    logger.info(f"Skipping step '{step.id}' (condition not met)")
                    continue

            # 执行步骤（带重试）
            step_result = await self._execute_step_with_retry(
                step, execution_context, step_results
            )
            step_results[step.id] = step_result

            if not step_result.success:
                logger.error(f"Step '{step.id}' failed after {step_result.attempt} attempts")
                if step_result.attempt >= step.max_retries:
                    pipeline_success = False
                    # 根据模板配置决定是否继续
                    if self._should_abort(template, step):
                        break

        # 4. 构建结果
        completed_at = datetime.now()
        duration = int((completed_at - started_at).total_seconds() * 1000)

        result = PipelineResult(
            template_name=template.name,
            success=pipeline_success,
            step_results=step_results,
            total_duration_ms=duration,
            started_at=started_at,
            completed_at=completed_at
        )

        # 5. 沉淀经验
        if self.memory:
            self.memory.store_experience(
                task_type=task_type,
                outcome='success' if pipeline_success else 'failed',
                data={
                    'template': template.name,
                    'duration_ms': duration,
                    'steps': {
                        sid: {
                            'success': sr.success,
                            'model': sr.model_used,
                            'attempts': sr.attempt
                        }
                        for sid, sr in step_results.items()
                    }
                }
            )

        # 6. 保存会话上下文
        if session_id:
            self.memory.set_session_context(
                session_id, 'last_pipeline', template.name
            )

        logger.info(
            f"Pipeline '{template.name}' completed: "
            f"{'SUCCESS' if pipeline_success else 'FAILED'} in {duration}ms"
        )

        return result

    async def _execute_step_with_retry(
        self,
        step: PipelineStep,
        context: Dict[str, Any],
        prev_results: Dict[str, StepResult]
    ) -> StepResult:
        """执行单个步骤（带重试）"""
        last_result = None

        for attempt in range(1, step.max_retries + 1):
            logger.info(f"Executing step '{step.id}', attempt {attempt}")
            
            step_result = await self._execute_single_step(
                step, context, prev_results, attempt
            )
            last_result = step_result

            if step_result.success:
                break
            
            logger.warning(
                f"Step '{step.id}' attempt {attempt} failed: {step_result.error}"
            )

        return last_result

    async def _execute_single_step(
        self,
        step: PipelineStep,
        context: Dict[str, Any],
        prev_results: Dict[str, StepResult],
        attempt: int
    ) -> StepResult:
        """执行单个步骤的单次尝试"""
        import time
        start_time = time.time()

        try:
            # 1. 选择模型
            model = None
            if step.agent:
                model = self.registry.select(
                    role=step.agent.role,
                    context=step.agent.model_selector
                )

            # 2. 构建步骤输入
            step_input = self._resolve_step_input(step, context, prev_results)

            # 3. 构建prompt
            prompt = self._build_step_prompt(step, model, step_input, context)

            # 4. 执行（通过回调或默认实现）
            if self._step_executor:
                output = await self._step_executor(step, model, prompt)
            else:
                # 默认：返回占位符
                logger.warning("No step executor configured, using placeholder")
                output = {"status": "placeholder", "prompt": prompt}

            duration_ms = int((time.time() - start_time) * 1000)

            return StepResult(
                step_id=step.id,
                success=True,
                output=output,
                duration_ms=duration_ms,
                model_used=model.id if model else None,
                attempt=attempt
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Step '{step.id}' execution error: {e}")
            
            return StepResult(
                step_id=step.id,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
                attempt=attempt
            )

    def _build_context(
        self,
        task_type: str,
        task_input: str,
        session_id: str = None,
        extra_context: Dict = None
    ) -> Dict[str, Any]:
        """构建执行上下文"""
        context = {
            'task_type': task_type,
            'task_input': task_input,
            'timestamp': datetime.now().isoformat(),
            'steps': {}  # 存储步骤输出
        }

        # 注入历史经验
        if self.memory:
            memories = self.memory.retrieve_similar(task_type, limit=2)
            context['history_context'] = self.memory.build_context_from_memories(memories)

        # 注入会话上下文
        if session_id and self.memory:
            session_data = self.memory.get_session_context(session_id)
            context['session'] = session_data

        # 合并额外上下文
        if extra_context:
            context.update(extra_context)

        return context

    def _evaluate_condition(
        self,
        condition: str,
        results: Dict[str, StepResult]
    ) -> bool:
        """
        评估条件表达式
        
        支持格式：
        - "{{ steps.review.output.issues|length > 0 }}"
        - "{{ steps.generate.success }}"
        """
        # 提取步骤引用
        match = re.search(r'steps\.(\w+)\.(\w+)', condition)
        if not match:
            return True  # 无条件默认通过
        
        step_id, key = match.groups()
        step_result = results.get(step_id)
        
        if not step_result:
            return False  # 步骤未执行

        # 简单条件评估
        if 'success' in condition:
            return step_result.success
        
        if 'length > 0' in condition:
            output = step_result.output
            if isinstance(output, dict):
                value = output.get(key, [])
                return len(value) > 0
            elif isinstance(output, list):
                return len(output) > 0
        
        # 默认通过
        return True

    def _resolve_step_input(
        self,
        step: PipelineStep,
        context: Dict,
        prev_results: Dict[str, StepResult]
    ) -> Any:
        """解析步骤输入"""
        if not step.input:
            return context.get('task_input', '')

        # 检查是否有数据来源
        if step.input.source:
            # 从之前的步骤输出获取
            match = re.match(r'steps\.(\w+)\.output\.?(\w+)?', step.input.source)
            if match:
                src_step_id, src_key = match.groups()
                src_result = prev_results.get(src_step_id)
                if src_result and src_result.output:
                    if src_key:
                        return src_result.output.get(src_key, '')
                    return src_result.output

        return step.input.data or context.get('task_input', '')

    def _build_step_prompt(
        self,
        step: PipelineStep,
        model: Optional[ModelSpec],
        step_input: Any,
        context: Dict
    ) -> str:
        """构建步骤prompt"""
        parts = []

        # 1. 历史经验
        if context.get('history_context'):
            parts.append(context['history_context'])

        # 2. 步骤动作描述
        if step.action:
            parts.append(f"## 任务\n\n请执行：{step.action}")

        # 3. 输入内容
        if isinstance(step_input, str):
            parts.append(f"## 输入\n\n{step_input}")
        else:
            parts.append(f"## 输入\n\n{str(step_input)}")

        return "\n\n".join(parts)

    def _should_abort(
        self,
        template: PipelineTemplate,
        failed_step: PipelineStep
    ) -> bool:
        """判断是否应该中止Pipeline"""
        # 默认：关键步骤失败则中止
        # 可通过模板metadata配置
        critical_steps = template.metadata.get('critical_steps', [])
        return failed_step.id in critical_steps

    def get_template_info(self) -> List[Dict]:
        """获取所有模板信息"""
        templates = self.templates.list_templates()
        return [
            {
                'name': t.name,
                'version': t.version,
                'description': t.description,
                'steps': t.get_step_ids(),
                'trigger': t.trigger.task_type if t.trigger else None
            }
            for t in templates
        ]
