"""
Harness 2.0 - Core Models Package
模型抽象层：统一模型注册、选择和fallback机制
"""

from .registry import ModelRegistry, ModelSpec

__all__ = ['ModelRegistry', 'ModelSpec']
