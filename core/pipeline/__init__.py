"""
Harness 2.0 - Core Pipeline Package
模板化Pipeline引擎：配置驱动的任务编排
"""

from .template import PipelineTemplate, TemplateLoader
from .engine import PipelineEngine

__all__ = ['PipelineTemplate', 'TemplateLoader', 'PipelineEngine']
