"""
Harness Orchestrator - 主编排器

整合所有核心模块：
- ModelRegistry: 模型选择和路由
- MemoryService: 记忆管理
- PipelineEngine: Pipeline执行
- MailGateway: 邮件网关

提供统一的任务编排接口
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from .models.registry import ModelRegistry
from .memory.service import MemoryService
from .memory.compressor import ContextCompressor
from .pipeline.engine import PipelineEngine
from .pipeline.template import PipelineTemplate
from .gateway.mail import MailGateway

logger = logging.getLogger(__name__)


class HarnessOrchestrator:
    """
    Harness主编排器
    
    核心职责：
    1. 初始化所有子模块
    2. 接收和执行任务
    3. 管理邮件网关
    4. 提供统一的API
    """
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        
        # 初始化各模块
        self.registry = self._init_model_registry()
        self.memory = self._init_memory_service()
        self.compressor = self._init_compressor()
        self.pipeline = self._init_pipeline_engine()
        self.gateway = self._init_mail_gateway()
        
        logger.info("Harness Orchestrator initialized")

    def _init_model_registry(self) -> ModelRegistry:
        """初始化模型注册表"""
        config_path = os.path.join(self.config_dir, "models.yaml")
        return ModelRegistry(config_path)

    def _init_memory_service(self) -> MemoryService:
        """初始化记忆服务"""
        db_path = "data/memory.db"
        return MemoryService(db_path)

    def _init_compressor(self) -> ContextCompressor:
        """初始化上下文压缩器"""
        return ContextCompressor()

    def _init_pipeline_engine(self) -> PipelineEngine:
        """初始化Pipeline引擎"""
        engine = PipelineEngine(
            registry=self.registry,
            memory=self.memory,
            compressor=self.compressor,
            template_dir="templates"
        )
        return engine

    def _init_mail_gateway(self) -> MailGateway:
        """初始化邮件网关"""
        config_path = os.path.join(self.config_dir, "gateway.yaml")
        return MailGateway(config_path)

    # --- 核心API ---

    async def run_task(
        self,
        task_type: str,
        task_input: str,
        template_name: str = None,
        session_id: str = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        运行单个任务
        
        Args:
            task_type: 任务类型 (code_generation/code_review/bug_fix等)
            task_input: 任务输入内容
            template_name: 指定模板名称（可选）
            session_id: 会话ID（可选）
            context: 额外上下文（可选）
            
        Returns:
            执行结果字典
        """
        logger.info(f"Running task: type={task_type}, input={task_input[:50]}...")

        try:
            # 获取模板
            template = None
            if template_name:
                template = self.pipeline.templates.get_template(template_name)
                if not template:
                    return {
                        'success': False,
                        'error': f'Template not found: {template_name}'
                    }

            # 执行Pipeline
            result = await self.pipeline.execute(
                task_type=task_type,
                task_input=task_input,
                template=template,
                session_id=session_id,
                context=context
            )

            # 转换为字典返回
            return {
                'success': result.success,
                'template_name': result.template_name,
                'total_duration_ms': result.total_duration_ms,
                'step_results': {
                    sid: {
                        'success': sr.success,
                        'model_used': sr.model_used,
                        'attempts': sr.attempt,
                        'duration_ms': sr.duration_ms,
                        'error': sr.error
                    }
                    for sid, sr in result.step_results.items()
                },
                'error': result.error,
                'started_at': result.started_at.isoformat() if result.started_at else None,
                'completed_at': result.completed_at.isoformat() if result.completed_at else None
            }

        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def run_from_email(
        self,
        subject: str,
        body: str,
        from_addr: str
    ) -> Dict[str, Any]:
        """
        从邮件运行任务
        
        Args:
            subject: 邮件主题
            body: 邮件正文
            from_addr: 发件人
            
        Returns:
            执行结果
        """
        # 1. 解析邮件为任务
        task = self.gateway.parse_email_to_task(subject, body, from_addr)
        
        if not task:
            # 无法解析，返回帮助
            help_content = self.gateway.generate_help_reply()
            await self.gateway.send_email(
                from_addr,
                "harness - Help",
                help_content
            )
            return {
                'success': False,
                'error': 'No valid command found',
                'help_sent': True
            }

        # 2. 执行任务
        result = await self.run_task(
            task_type=task['task_type'],
            task_input=task['input'],
            context={'source': 'email'}
        )

        # 3. 发送响应邮件
        task['id'] = result.get('template_name', 'task')
        await self.gateway.send_task_response(task, result)

        return result

    # --- 查询API ---

    def list_templates(self) -> List[Dict[str, Any]]:
        """列出所有可用模板"""
        return self.pipeline.get_template_info()

    def list_models(self, role: str = None) -> List[Dict[str, Any]]:
        """列出所有可用模型"""
        if role:
            models = self.registry.get_models_for_role(role)
        else:
            models = self.registry.get_all_models()
        
        return [
            {
                'id': m.id,
                'roles': m.roles,
                'cost_per_1k': m.cost_per_1k,
                'quality_score': m.quality_score,
                'provider': m.provider,
                'cli_command': m.cli_command
            }
            for m in models
        ]

    def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        return self.memory.get_statistics()

    def get_gateway_stats(self) -> Dict[str, Any]:
        """获取网关统计"""
        return self.gateway.get_stats()

    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        return {
            'templates': len(self.pipeline.templates.list_templates()),
            'models': len(self.registry.get_all_models()),
            'memory': self.memory.get_statistics(),
            'gateway': self.gateway.get_stats()
        }

    # --- 邮件监听循环（独立运行） ---

    async def start_email_listener(self, poll_interval: int = 30):
        """
        启动邮件监听
        
        Args:
            poll_interval: 轮询间隔（秒）
        """
        if not self.gateway.is_enabled():
            logger.warning("Mail gateway not enabled, skipping listener")
            return

        logger.info(f"Starting email listener (interval: {poll_interval}s)")

        while True:
            try:
                # 这里需要接入MailMindHub的邮件获取API
                # 当前是占位实现
                await self._check_and_process_emails()
            except Exception as e:
                logger.error(f"Email listener error: {e}")
            
            await asyncio.sleep(poll_interval)

    async def _check_and_process_emails(self):
        """检查并处理新邮件（需要MailMindHub API支持）"""
        # TODO: 实现MailMindHub邮件获取逻辑
        # 示例框架：
        # emails = await self.gateway.fetch_new_emails()
        # for email in emails:
        #     await self.run_from_email(email.subject, email.body, email.from_addr)
        pass

    # --- 配置管理 ---

    def reload_config(self):
        """重新加载所有配置"""
        self.registry.reload()
        self.pipeline.templates.reload()
        logger.info("All configurations reloaded")

    def set_step_executor(self, executor_func):
        """
        设置步骤执行器
        
        Args:
            executor_func: async function(step, model, prompt) -> result
        """
        self.pipeline.set_step_executor(executor_func)


# --- CLI入口 ---

async def main():
    """CLI入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Harness 2.0 Orchestrator')
    parser.add_argument('--config-dir', default='config', help='配置目录')
    parser.add_argument('--action', choices=['info', 'templates', 'models', 'run'], 
                       default='info', help='操作')
    parser.add_argument('--task-type', help='任务类型')
    parser.add_argument('--input', help='任务输入')
    parser.add_argument('--template', help='模板名称')
    
    args = parser.parse_args()
    
    orchestrator = HarnessOrchestrator(args.config_dir)
    
    if args.action == 'info':
        info = orchestrator.get_system_info()
        print("Harness 2.0 System Info:")
        print(f"  Templates: {info['templates']}")
        print(f"  Models: {info['models']}")
        print(f"  Memory: {info['memory']}")
        print(f"  Gateway: {info['gateway']}")
        
    elif args.action == 'templates':
        templates = orchestrator.list_templates()
        print("Available Templates:")
        for t in templates:
            print(f"  - {t['name']} v{t.get('version', 1)}: {t.get('description', '')}")
            
    elif args.action == 'models':
        models = orchestrator.list_models()
        print("Available Models:")
        for m in models:
            print(f"  - {m['id']} ({', '.join(m['roles'])}): "
                  f"cost={m['cost_per_1k']}, quality={m['quality_score']}")
    
    elif args.action == 'run':
        if not args.task_type or not args.input:
            print("Error: --task-type and --input required for 'run' action")
            return
        
        result = await orchestrator.run_task(
            task_type=args.task_type,
            task_input=args.input,
            template_name=args.template
        )
        
        print(f"Task Result: {'SUCCESS' if result['success'] else 'FAILED'}")
        if result.get('error'):
            print(f"Error: {result['error']}")


if __name__ == '__main__':
    asyncio.run(main())
