"""core/tools/operators/file.py
FileOperator - basic file operations (list/read/write)
"""

import asyncio
import time
from pathlib import Path
from typing import Dict, Any, List

from ..base import BaseTool, ToolCategory, ToolParam, ToolResult


class FileOperator(BaseTool):
    name = "file_operator"
    description = "Basic file operations within work_dir"
    category = ToolCategory.OPERATOR
    params = [
        ToolParam("action", "string", "list/read/write", required=True, enum=["list", "read", "write"]),
        ToolParam("path", "string", "path relative to work_dir", required=False, default="."),
        ToolParam("content", "string", "content for write", required=False, default=""),
    ]

    async def run(self, params: Dict[str, Any], work_dir: str = ".") -> ToolResult:
        start = time.time()
        action = params.get("action")
        rel = params.get("path") or "."
        p = Path(work_dir) / rel

        try:
            if action == "list":
                if p.is_dir():
                    items = [str(x.name) for x in sorted(p.iterdir())]
                else:
                    items = [str(p.name)] if p.exists() else []
                return ToolResult(success=True, output=items, duration_ms=int((time.time()-start)*1000))

            if action == "read":
                if not p.exists():
                    return ToolResult(success=False, error=f"path not found: {p}", duration_ms=int((time.time()-start)*1000))
                text = p.read_text(encoding="utf-8")
                return ToolResult(success=True, output=text, duration_ms=int((time.time()-start)*1000))

            if action == "write":
                content = params.get("content", "")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                return ToolResult(success=True, output=str(p), artifacts=[str(p)], duration_ms=int((time.time()-start)*1000))

            return ToolResult(success=False, error=f"unsupported action: {action}", duration_ms=int((time.time()-start)*1000))

        except Exception as e:
            return ToolResult(success=False, error=str(e), duration_ms=int((time.time()-start)*1000))
