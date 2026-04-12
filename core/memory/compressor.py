"""
Context Compressor - 上下文压缩器

当上下文接近token限制时，自动压缩历史内容，
保留关键信息，去除冗余。
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class ContextCompressor:
    """
    上下文压缩器
    
    功能：
    - 检测token使用率
    - 自动压缩历史上下文
    - 保留关键决策点
    """
    
    def __init__(
        self,
        max_tokens: int = 8000,
        compression_trigger: float = 0.8,
        model_strategy: str = 'cost_aware'
    ):
        self.max_tokens = max_tokens
        self.compression_trigger = compression_trigger
        self.model_strategy = model_strategy

    def should_compress(self, current_tokens: int) -> bool:
        """
        检查是否需要压缩
        
        Args:
            current_tokens: 当前token数
            
        Returns:
            是否应该触发压缩
        """
        ratio = current_tokens / self.max_tokens if self.max_tokens > 0 else 0
        return ratio >= self.compression_trigger

    def compress_simple(
        self,
        context_parts: List[Dict[str, str]],
        target_tokens: int = None
    ) -> str:
        """
        简单压缩：基于长度截断和优先级
        
        Args:
            context_parts: 上下文片段列表 [{'type': str, 'content': str, 'priority': int}]
            target_tokens: 目标token数
            
        Returns:
            压缩后的文本
        """
        if target_tokens is None:
            target_tokens = int(self.max_tokens * 0.7)  # 压缩到70%
        
        # 按优先级排序（数字越小越重要）
        sorted_parts = sorted(
            context_parts,
            key=lambda x: x.get('priority', 999)
        )
        
        result_parts = []
        current_tokens = 0
        
        for part in sorted_parts:
            content = part.get('content', '')
            part_tokens = len(content) // 4  # 粗略估算
            
            if current_tokens + part_tokens <= target_tokens:
                # 完整保留
                result_parts.append(content)
                current_tokens += part_tokens
            else:
                # 截断保留
                remaining = target_tokens - current_tokens
                if remaining > 100:  # 至少保留100tokens
                    truncated = content[:remaining * 4]
                    result_parts.append(f"{truncated}\n...[truncated]...")
                    current_tokens += remaining
                    break
        
        return "\n\n".join(result_parts)

    def compress_with_summary(
        self,
        full_context: str,
        summary_length: int = 500
    ) -> str:
        """
        生成摘要式压缩（需要LLM支持，这里提供框架）
        
        Args:
            full_context: 完整上下文
            summary_length: 摘要长度
            
        Returns:
            压缩后的上下文
        """
        # 简单实现：截取首尾关键部分
        if len(full_context) <= summary_length * 4:
            return full_context
        
        head = full_context[:summary_length * 2]
        tail = full_context[-summary_length * 2:]
        
        return f"{head}\n\n...[中间内容已压缩]...\n\n{tail}"

    def build_prompt_with_compression(
        self,
        system_prompt: str,
        task_content: str,
        history_memories: List[Dict] = None,
        current_tokens: int = None
    ) -> str:
        """
        构建带压缩的prompt
        
        Args:
            system_prompt: 系统提示
            task_content: 任务内容
            history_memories: 历史记忆
            current_tokens: 当前token估算
            
        Returns:
            完整的prompt
        """
        parts = []
        
        # 1. 系统提示（总是保留）
        parts.append(system_prompt)
        
        # 2. 历史记忆（可能需要压缩）
        if history_memories:
            history_text = self._format_memories(history_memories)
            history_tokens = len(history_text) // 4
            
            if current_tokens and self.should_compress(current_tokens):
                logger.info("Compressing history memories due to token limit")
                history_text = self.compress_with_summary(history_text)
            
            parts.append(history_text)
        
        # 3. 任务内容（总是保留）
        parts.append(f"## 当前任务\n\n{task_content}")
        
        return "\n\n".join(parts)

    @staticmethod
    def _format_memories(memories: List[Dict]) -> str:
        """格式化记忆为文本"""
        if not memories:
            return ""
        
        parts = []
        for mem in memories:
            if mem.get('outcome') == 'success' and mem.get('template'):
                template = mem['template']
                if isinstance(template, str):
                    parts.append(f"### 成功案例\n{template}")
                else:
                    parts.append(f"### 成功案例\n{template}")
            elif mem.get('outcome') == 'failed' and mem.get('lesson'):
                parts.append(f"### 失败教训\n{mem['lesson']}")
        
        if not parts:
            return ""
        
        return "## 历史经验\n\n" + "\n\n".join(parts)

    def estimate_tokens(self, text: str) -> int:
        """
        估算token数量
        
        Args:
            text: 文本内容
            
        Returns:
            估算的token数
        """
        # 简单估算：英文约4字符/token，中文约1.5字符/token
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        return chinese_chars + other_chars // 4
