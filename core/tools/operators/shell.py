"""core/tools/operators/shell.py
ShellExecutor - executes shell commands when approved. requires_approval=True
"""

import asyncio
import subprocess
import time
import shlex
from pathlib import Path
from typing import Dict, Any, List

from ..base import BaseTool, ToolCategory, ToolParam, ToolResult


class ShellExecutor(BaseTool):
    name = "shell_executor"
    description = "Execute shell commands (requires approval)"
    category = ToolCategory.OPERATOR
    requires_approval = True

    params = [
        ToolParam("command", "string", "command to run (single string)", required=True),
        ToolParam("args", "array", "additional args (list)", required=False, default=[]),
        ToolParam("approved", "boolean", "must be true to allow execution", required=False, default=False),
        ToolParam("timeout", "integer", "timeout seconds", required=False, default=30),
    ]

    async def run(self, params: Dict[str, Any], work_dir: str = ".") -> ToolResult:
        start = time.time()
        cmd = params.get("command")
        args = params.get("args", []) or []
        approved = bool(params.get("approved", False))
        timeout = int(params.get("timeout", 30))

        if not approved:
            return ToolResult(success=False, error="Shell execution requires approval (set approved=true)", duration_ms=int((time.time()-start)*1000))

        # build list
        if isinstance(args, list):
            cmd_list = [cmd] + args
        else:
            # if args provided as string, split
            cmd_list = [cmd] + shlex.split(str(args))

        def _run():
            proc = subprocess.run(cmd_list, capture_output=True, text=True, cwd=work_dir, timeout=timeout)
            return proc

        try:
            proc = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"Command timed out after {timeout}s", duration_ms=int((time.time()-start)*1000))
        except Exception as e:
            return ToolResult(success=False, error=str(e), duration_ms=int((time.time()-start)*1000))

        success = proc.returncode == 0
        output = proc.stdout.strip() if proc.stdout else ""
        err = proc.stderr.strip() if proc.stderr else None
        return ToolResult(success=success, output=output if success else None, error=None if success else (err or proc.stdout), duration_ms=int((time.time()-start)*1000))
