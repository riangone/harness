"""core/tools/registry.py
Simple ToolRegistry implementation.
"""
from typing import Dict, List, Optional
from .base import BaseTool, ToolCategory


class ToolRegistry:
    _instance: Optional["ToolRegistry"] = None

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = cls()
            # defer default registration to avoid import errors
            try:
                cls._instance._register_defaults()
            except Exception:
                pass
        return cls._instance

    def _register_defaults(self):
        """Register default tools available in the harness.
        Imports are done lazily and failures are ignored to allow partial availability in tests.
        """
        try:
            from .renderers.marp import MarpRenderer
            from .renderers.pdf import PDFRenderer
            from .renderers.pptx import PPTXRenderer
            from .renderers.excel import ExcelRenderer
            from .renderers.docx import DocxRenderer
            from .operators.browser import BrowserOperator
            from .operators.http import HttpCaller
            from .operators.file import FileOperator
            from .operators.shell import ShellExecutor
        except Exception as e:
            # If imports fail (missing deps), skip registration but log the issue
            import logging
            logging.getLogger(__name__).warning(f"Skipping default tool registration due to import error: {e}")
            return

        defaults = [
            MarpRenderer(), PDFRenderer(), PPTXRenderer(),
            ExcelRenderer(), DocxRenderer(), BrowserOperator(), HttpCaller(), FileOperator(), ShellExecutor()
        ]
        for tool in defaults:
            try:
                self.register(tool)
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception(f"Failed to register tool {getattr(tool, 'name', tool)}: {e}")

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_all(self) -> List[BaseTool]:
        return list(self._tools.values())

    def list_by_category(self, category: ToolCategory) -> List[BaseTool]:
        return [t for t in self._tools.values() if t.category == category]

    def get_schemas_for_llm(self, names: List[str] = None) -> List[dict]:
        tools = self.list_all() if names is None else [self._tools[n] for n in names if n in self._tools]
        return [t.get_schema() for t in tools]
