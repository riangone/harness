"""core/tools/renderers/docx.py
DocxRenderer - uses scripts/tools/render_docx.py
"""

import asyncio
import subprocess
import time
import sys
from pathlib import Path
from typing import Dict, Any

from ..base import BaseTool, ToolCategory, ToolParam, ToolResult


class DocxRenderer(BaseTool):
    name = "docx_renderer"
    description = "Render Markdown to .docx using python-docx"
    category = ToolCategory.RENDERER
    params = [
        ToolParam("input_file", "string", "input markdown file", required=True),
        ToolParam("output_file", "string", "output docx file", required=True),
    ]

    async def run(self, params: Dict[str, Any], work_dir: str = ".") -> ToolResult:
        start = time.time()
        input_file = Path(work_dir) / params.get("input_file")
        output_file = Path(work_dir) / params.get("output_file")

        if not input_file.exists():
            return ToolResult(success=False, error=f"input not found: {input_file}", duration_ms=int((time.time()-start)*1000))

        def _run():
            cmd = [sys.executable, str(Path.cwd() / "scripts" / "tools" / "render_docx.py"), "--input", str(input_file), "--output", str(output_file)]
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir)
            return proc

        try:
            proc = await asyncio.to_thread(_run)
        except Exception as e:
            return ToolResult(success=False, error=str(e), duration_ms=int((time.time()-start)*1000))

        success = proc.returncode == 0
        size = output_file.stat().st_size if success and output_file.exists() else 0
        return ToolResult(success=success, output=str(output_file) if success else None, error=None if success else (proc.stderr or proc.stdout), duration_ms=int((time.time()-start)*1000), metadata={"size_bytes": size}, artifacts=[str(output_file)] if success else [])
