"""core/tools/renderers/pptx.py
PPTXRenderer - uses scripts/tools/render_pptx.py
"""

import asyncio
import subprocess
import time
import sys
from pathlib import Path
from typing import Dict, Any

from ..base import BaseTool, ToolCategory, ToolParam, ToolResult


class PPTXRenderer(BaseTool):
    name = "pptx_renderer"
    description = "Render JSON/Markdown to .pptx using python-pptx"
    category = ToolCategory.RENDERER
    params = [
        ToolParam("input_file", "string", "input json or markdown file", required=True),
        ToolParam("output_file", "string", "output pptx file", required=True),
    ]

    async def run(self, params: Dict[str, Any], work_dir: str = ".") -> ToolResult:
        start = time.time()
        input_file = Path(work_dir) / params.get("input_file")
        output_file = Path(work_dir) / params.get("output_file")

        if not input_file.exists():
            return ToolResult(success=False, error=f"input not found: {input_file}", duration_ms=int((time.time()-start)*1000))

        def _run():
            # .venv_pptx に python-pptx がインストールされている場合はそちらを優先使用
            harness_root = Path(__file__).resolve().parents[3]
            venv_python = harness_root / ".venv_pptx" / "bin" / "python"
            python_exe = str(venv_python) if venv_python.exists() else sys.executable
            cmd = [python_exe, str(harness_root / "scripts" / "tools" / "render_pptx.py"), "--input", str(input_file), "--output", str(output_file)]
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir)
            return proc

        try:
            proc = await asyncio.to_thread(_run)
        except Exception as e:
            return ToolResult(success=False, error=str(e), duration_ms=int((time.time()-start)*1000))

        success = proc.returncode == 0
        size = output_file.stat().st_size if success and output_file.exists() else 0
        return ToolResult(success=success, output=str(output_file) if success else None, error=None if success else (proc.stderr or proc.stdout), duration_ms=int((time.time()-start)*1000), metadata={"size_bytes": size}, artifacts=[str(output_file)] if success else [])
