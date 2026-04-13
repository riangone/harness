"""core/tools/operators/browser.py
BrowserOperator - wraps scripts/tools/browser_action.py (Playwright)
"""

import asyncio
import subprocess
import time
import sys
from pathlib import Path
from typing import Dict, Any

from ..base import BaseTool, ToolCategory, ToolParam, ToolResult


class BrowserOperator(BaseTool):
    name = "browser_operator"
    description = "Browser operations (screenshot) via Playwright"
    category = ToolCategory.OPERATOR
    params = [
        ToolParam("action", "string", "action to perform", required=True, enum=["screenshot"]),
        ToolParam("url", "string", "target url", required=True),
        ToolParam("output_file", "string", "output file path", required=True),
        ToolParam("wait_ms", "integer", "wait milliseconds before capture", required=False, default=1000),
    ]

    async def run(self, params: Dict[str, Any], work_dir: str = ".") -> ToolResult:
        start = time.time()
        action = params.get("action")
        url = params.get("url")
        output_file = Path(work_dir) / params.get("output_file")
        wait_ms = int(params.get("wait_ms", 1000))

        def _run():
            cmd = [sys.executable, str(Path.cwd() / "scripts" / "tools" / "browser_action.py"), "--action", action, "--url", url, "--output", str(output_file), "--wait-ms", str(wait_ms)]
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir)
            return proc

        try:
            proc = await asyncio.to_thread(_run)
        except Exception as e:
            return ToolResult(success=False, error=str(e), duration_ms=int((time.time()-start)*1000))

        success = proc.returncode == 0
        size = output_file.stat().st_size if success and output_file.exists() else 0
        return ToolResult(success=success, output=str(output_file) if success else None, error=None if success else (proc.stderr or proc.stdout), duration_ms=int((time.time()-start)*1000), metadata={"size_bytes": size}, artifacts=[str(output_file)] if success else [])
