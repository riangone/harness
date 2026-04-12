"""
Mail Gateway - 邮件解析与响应格式化

本模块不负责 SMTP/IMAP 收发邮件，仅提供：
1. 邮件内容 → harness task 的转换（路由规则匹配）
2. task 结果 → 邮件正文的格式化（用于回调通知 MailMindHub）

实际的邮件收发由 MailMindHub 负责。
"""

import os
import re
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from pathlib import Path

try:
    from jinja2 import Template
except ImportError:
    class Template:
        def __init__(self, template_str: str):
            self.template = template_str

        def render(self, **kwargs) -> str:
            result = self.template
            for key, value in kwargs.items():
                result = result.replace(f"{{{key}}}", str(value))
            return result

logger = logging.getLogger(__name__)


@dataclass
class RoutingRule:
    """路由规则"""
    pattern: str
    action: str
    pipeline: str = None
    task_type: str = None
    reply_template: str = None


class MailGateway:
    """
    邮件网关：连接 MailMindHub 和 harness

    功能：
    - 解析入站邮件为 harness 任务
    - 路由规则匹配
    - 格式化出站邮件响应
    """

    def __init__(self, config_path: str = "config/gateway.yaml"):
        self.config = self._load_config(config_path)
        self.rules = self._parse_rules()
        self.response_template = self._load_template()

    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        import yaml

        if not os.path.exists(config_path):
            logger.warning(f"Config not found: {config_path}, using defaults")
            return self._default_config()

        with open(config_path) as f:
            return yaml.safe_load(f)

    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            'mail': {
                'routing_rules': [
                    {
                        'pattern': r'^(review|/review)\s+(.+)',
                        'action': 'create_task',
                        'pipeline': 'code_review',
                        'task_type': 'code_review'
                    },
                    {
                        'pattern': r'^(generate|/generate|/gen|/g)\s+(.+)',
                        'action': 'create_task',
                        'pipeline': 'code_generation',
                        'task_type': 'code_generation'
                    },
                    {
                        'pattern': r'^(fix|/fix)\s+(.+)',
                        'action': 'create_task',
                        'pipeline': 'bug_fix',
                        'task_type': 'bug_fix'
                    },
                    {
                        'pattern': r'^(help|/help|\?)',
                        'action': 'reply_help'
                    }
                ],
                'response_template': '''✅ **任务完成**

**任务**: {{ task_summary }}
**耗时**: {{ duration }}秒
**状态**: {{ status }}

**执行步骤**:
{{ result_summary }}
---
💡 回复此邮件可继续对话'''
            }
        }

    def _parse_rules(self) -> List[RoutingRule]:
        """解析路由规则"""
        rules_config = self.config.get('mail', {}).get('routing_rules', [])
        rules = []

        for rule_cfg in rules_config:
            rule = RoutingRule(
                pattern=rule_cfg['pattern'],
                action=rule_cfg['action'],
                pipeline=rule_cfg.get('pipeline'),
                task_type=rule_cfg.get('task_type', rule_cfg.get('pipeline')),
                reply_template=rule_cfg.get('reply_template')
            )
            rules.append(rule)

        return rules

    def _load_template(self) -> Template:
        """加载响应模板"""
        template_str = self.config.get('mail', {}).get(
            'response_template',
            "Task #{task_id} completed: {task_summary}"
        )
        return Template(template_str)

    # --- 入站邮件处理 ---

    def match_routing_rule(
        self,
        subject: str,
        body: str
    ) -> Optional[RoutingRule]:
        """
        匹配路由规则

        Args:
            subject: 邮件主题
            body: 邮件正文

        Returns:
            匹配的规则，如果没有匹配则返回None
        """
        content = f"{subject}\n{body}"

        for rule in self.rules:
            if re.search(rule.pattern, content, re.IGNORECASE | re.MULTILINE):
                return rule

        return None

    def parse_email_to_task(
        self,
        subject: str,
        body: str,
        from_addr: str = None,
        callback_url: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        邮件 → harness task 转换

        Args:
            subject: 邮件主题
            body: 邮件正文
            from_addr: 发件人地址
            callback_url: Webhook 回调地址（可选）

        Returns:
            任务字典，如果无法解析则返回None
        """
        rule = self.match_routing_rule(subject, body)

        if not rule:
            logger.info(f"No routing rule matched for email: {subject}")
            return None

        if rule.action != 'create_task':
            logger.info(f"Rule action is not create_task: {rule.action}")
            return None

        task_content = self._extract_task_content_from_subject_and_body(subject, body, rule.pattern)

        task = {
            'source': 'email',
            'from_addr': from_addr,
            'pipeline': rule.pipeline,
            'task_type': rule.task_type or rule.pipeline,
            'input': task_content,
            'subject': subject,
            'callback_url': callback_url,
            'metadata': {
                'rule_matched': rule.pattern,
                'action': rule.action,
                'from_addr': from_addr
            }
        }

        logger.info(f"Parsed email to task: pipeline={rule.pipeline}, task_type={task['task_type']}")
        return task

    def _extract_task_content_from_subject_and_body(self, subject: str, body: str, pattern: str) -> str:
        """从邮件主题和正文提取任务内容，优先主题"""
        # 首先尝试从 subject 提取
        subject_match = re.search(pattern, subject, re.IGNORECASE | re.MULTILINE)
        if subject_match and subject_match.lastindex and subject_match.lastindex >= 2:
            return subject_match.group(2).strip()

        # 如果 subject 提取失败，再尝试从 body 提取
        body_match = re.search(pattern, body, re.IGNORECASE | re.MULTILINE)
        if body_match and body_match.lastindex and body_match.lastindex >= 2:
            return body_match.group(2).strip()

        # 如果两者都未能精确提取，返回非空的 subject 或 body（如果存在的话）
        # 优先返回 subject，因为 subject 通常包含更直接的指令
        if subject.strip():
            return subject.strip()
        return body.strip()

    def generate_help_reply(self) -> str:
        """生成帮助回复"""
        return """🤖 harness - AI Agent Orchestrator

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

提示：
- 直接描述你的需求也可以
- 支持多轮对话，回复本邮件可继续

---
harness AI Orchestrator"""

    # --- 出站邮件格式化 ---

    def format_task_complete_response(
        self,
        task: Dict[str, Any],
        result: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        task 完成 → 格式化邮件正文（供 MailMindHub 发送）

        Args:
            task: 任务信息
            result: 执行结果

        Returns:
            邮件内容 {'subject': str, 'body': str}
        """
        task_id = task.get('id', 'N/A')
        task_summary = task.get('input', task.get('title', ''))[:100]
        duration = result.get('duration_ms', 0) // 1000 if result.get('duration_ms') else result.get('duration', 0)
        status = '✅ Success' if result.get('success') else '❌ Failed'

        # 构建结果摘要
        result_summary = ""
        if result.get('step_results'):
            for step_id, step_result in result['step_results'].items():
                icon = '✅' if step_result.get('success') else '❌'
                result_summary += f"{icon} {step_id}"
                if step_result.get('model_used'):
                    result_summary += f" ({step_result['model_used']})"
                result_summary += "\n"
        elif result.get('result'):
            result_summary = str(result['result'])[:500]

        # 渲染模板
        try:
            body = self.response_template.render(
                task_id=task_id,
                task_summary=task_summary,
                duration=duration,
                status=status,
                result_summary=result_summary,
                result=result
            )
        except Exception as e:
            logger.error(f"Template render error: {e}")
            body = f"Task #{task_id} completed: {status}"

        subject = f"[harness] Task #{task_id} {'✅' if result.get('success') else '❌ Failed'}"

        return {
            'subject': subject,
            'body': body
        }

    # --- 辅助方法 ---

    def get_stats(self) -> Dict[str, Any]:
        """获取网关统计信息"""
        return {
            'rules_count': len(self.rules),
            'pipelines': list(set(r.pipeline for r in self.rules if r.pipeline))
        }
