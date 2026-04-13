"""core/tools/renderers/marp.py
MarpRenderer - wrapper around scripts/tools/render_marp.py
"""

import asyncio
import subprocess
import shutil
import time
import sys
from pathlib import Path
from typing import Dict, Any

from ..base import BaseTool, ToolCategory, ToolParam, ToolResult


class MarpRenderer(BaseTool):
    name = "marp_renderer"
    description = "Render Marp Markdown to PDF/HTML/PPTX using Marp CLI"
    category = ToolCategory.RENDERER
    requires_approval = False

    params = [
        ToolParam("input_file", "string", "input markdown file path", required=True),
        ToolParam("output_file", "string", "output file path", required=True),
        ToolParam("format", "string", "output format", required=False, default="pdf", enum=["pdf", "html", "pptx"]),
        ToolParam("theme", "string", "marp theme", required=False, default="default"),
        ToolParam("auto_inject_frontmatter", "boolean", "auto inject frontmatter if missing", required=False, default=True),
        ToolParam("allow_local_files", "boolean", "allow local files", required=False, default=True),
    ]

    async def run(self, params: Dict[str, Any], work_dir: str = ".") -> ToolResult:
        start = time.time()

        # check marp availability
        if not shutil.which("marp"):
            return ToolResult(success=False, error="marp command not found. Install: npm install -g @marp-team/marp-cli", duration_ms=int((time.time()-start)*1000))

        input_file = Path(work_dir) / params.get("input_file")
        output_file = Path(work_dir) / params.get("output_file")
        fmt = params.get("format", "pdf")
        theme = params.get("theme")
        allow_local = params.get("allow_local_files", True)
        auto_inject = params.get("auto_inject_frontmatter", True)

        if not input_file.exists():
            return ToolResult(success=False, error=f"input not found: {input_file}", duration_ms=int((time.time()-start)*1000))

        def _run():
            cmd = [sys.executable, str(Path.cwd() / "scripts" / "tools" / "render_marp.py"), "--input", str(input_file), "--output", str(output_file), "--format", fmt]
            if theme:
                cmd.extend(["--theme", theme])
            if not allow_local:
                cmd.append("--no-allow-local-files")
            if not auto_inject:
                cmd.append("--no-auto-inject-frontmatter")
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir)
            return proc

        try:
            proc = await asyncio.to_thread(_run)
        except Exception as e:
            return ToolResult(success=False, error=str(e), duration_ms=int((time.time()-start)*1000))

        success = proc.returncode == 0
        size = output_file.stat().st_size if success and output_file.exists() else 0
        metadata = {"format": fmt, "size_bytes": size}
        return ToolResult(success=success, output=str(output_file) if success else None, error=None if success else (proc.stderr or proc.stdout), duration_ms=int((time.time()-start)*1000), metadata=metadata, artifacts=[str(output_file)] if success else [])
