"""
Harness 2.0 - Core Memory Package
轻量记忆系统：任务经验沉淀和上下文注入
"""

from .service import MemoryService
from .compressor import ContextCompressor
from .auto_improve import (
    build_lesson,
    check_and_update_agents_md,
    register_skill,
    retrieve_skill,
    collect_project_context,
)

__all__ = [
    'MemoryService',
    'ContextCompressor',
    'build_lesson',
    'check_and_update_agents_md',
    'register_skill',
    'retrieve_skill',
    'collect_project_context',
]
