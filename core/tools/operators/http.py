"""core/tools/operators/http.py
HttpCaller - wraps scripts/tools/http_call.py
"""

import asyncio
import subprocess
import time
import sys
import json
from pathlib import Path
from typing import Dict, Any

from ..base import BaseTool, ToolCategory, ToolParam, ToolResult


class HttpCaller(BaseTool):
    name = "http_caller"
    description = "Make external HTTP calls"
    category = ToolCategory.OPERATOR
    params = [
        ToolParam("method", "string", "HTTP method", required=True),
        ToolParam("url", "string", "URL", required=True),
        ToolParam("body", "string", "JSON body string", required=False, default=""),
        ToolParam("headers", "string", "JSON headers string", required=False, default="{}"),
        ToolParam("timeout", "integer", "timeout seconds", required=False, default=30),
    ]

    async def run(self, params: Dict[str, Any], work_dir: str = ".") -> ToolResult:
        start = time.time()
        method = params.get("method")
        url = params.get("url")
        body = params.get("body", "")
        headers = params.get("headers", "{}")
        timeout = int(params.get("timeout", 30))

        def _run():
            cmd = [sys.executable, str(Path.cwd() / "scripts" / "tools" / "http_call.py"), "--method", method, "--url", url, "--body", body, "--headers", headers, "--timeout", str(timeout)]
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir)
            return proc

        try:
            proc = await asyncio.to_thread(_run)
        except Exception as e:
            return ToolResult(success=False, error=str(e), duration_ms=int((time.time()-start)*1000))

        # try parse JSON
        try:
            data = json.loads(proc.stdout or proc.stderr)
        except Exception:
            data = {"success": False, "output": proc.stdout, "error": proc.stderr}

        success = data.get("success", False)
        output = data.get("output")
        return ToolResult(success=success, output=output, error=data.get("error"), duration_ms=int((time.time()-start)*1000), metadata={"status_code": data.get("status_code")})
