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
        # Intentionally empty for now; concrete renderers will register themselves
        return

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
