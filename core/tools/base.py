"""core/tools/base.py
Base classes for tool implementations.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod
from enum import Enum


class ToolCategory(str, Enum):
    RENDERER = "renderer"
    OPERATOR = "operator"
    ANALYZER = "analyzer"
    RETRIEVER = "retriever"


@dataclass
class ToolParam:
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: List[Any] = field(default_factory=list)


@dataclass
class ToolResult:
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    category: ToolCategory = ToolCategory.RENDERER
    params: List[ToolParam] = []
    requires_approval: bool = False

    def get_schema(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    p.name: {
                        "type": p.type,
                        "description": p.description,
                        **({"enum": p.enum} if p.enum else {}),
                        **({"default": p.default} if p.default is not None else {}),
                    }
                    for p in self.params
                },
                "required": [p.name for p in self.params if p.required]
            }
        }

    @abstractmethod
    async def run(self, params: Dict[str, Any], work_dir: str = ".") -> ToolResult:
        raise NotImplementedError

    def validate_params(self, params: Dict) -> Optional[str]:
        for p in self.params:
            if p.required and p.name not in params:
                return f"required param '{p.name}' missing"
            if p.enum and params.get(p.name) not in p.enum:
                return f"'{p.name}' must be one of {p.enum}"
        return None
