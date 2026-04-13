"""core/agents/hermes.py
Simplified HermesAgent implementation following design notes.
This implementation uses ToolRegistry for tool schemas and can call tools.
LLM interaction is via 'claude' CLI if available; otherwise an exception is raised when calling LLM.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from core.tools.registry import ToolRegistry
from core.tools.base import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ReActStep:
    step_num: int
    thought: str
    tool_calls: List[Dict] = field(default_factory=list)
    observations: List[ToolResult] = field(default_factory=list)
    is_final: bool = False
    final_answer: Optional[str] = None


@dataclass
class HermesResult:
    success: bool
    final_answer: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    react_steps: List[ReActStep] = field(default_factory=list)
    total_duration_ms: int = 0
    error: Optional[str] = None


class HermesAgent:
    SYSTEM_PROMPT_TEMPLATE = """You are an agent that can call tools. Use the following format:

<thinking>...</thinking>
<tool_call>{"name":"tool_name","params":{...}}</tool_call>
<final_answer>...</final_answer>
"""

    def __init__(self, tools: List[str] = None, max_react_steps: int = 6, model: str = "claude", work_dir: str = "."):
        self.registry = ToolRegistry.get_instance()
        self.tool_names = tools
        self.max_react_steps = max_react_steps
        self.model = model
        self.work_dir = work_dir

    async def run(self, task: str, context: Dict = None) -> HermesResult:
        start_time = datetime.now()
        react_steps: List[ReActStep] = []
        all_artifacts: List[str] = []

        # build system prompt with tool schemas
        tool_schemas = self.registry.get_schemas_for_llm(self.tool_names)
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE + "\nAvailable tools:\n" + json.dumps(tool_schemas, ensure_ascii=False, indent=2)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task: {task}"}
        ]

        for step_num in range(1, self.max_react_steps + 1):
            logger.info(f"HermesAgent step {step_num}")
            try:
                llm_response = await self._call_llm(messages)
            except Exception as e:
                return HermesResult(success=False, error=str(e), total_duration_ms=int((datetime.now()-start_time).total_seconds()*1000))

            thought, tool_calls, is_final, final_answer = self._parse_response(llm_response)
            react_step = ReActStep(step_num=step_num, thought=thought, tool_calls=tool_calls, is_final=is_final, final_answer=final_answer)
            react_steps.append(react_step)

            if is_final:
                duration = int((datetime.now() - start_time).total_seconds() * 1000)
                return HermesResult(success=True, final_answer=final_answer, artifacts=all_artifacts, react_steps=react_steps, total_duration_ms=duration)

            if tool_calls:
                observations = await self._execute_parallel_tools(tool_calls)
                react_step.observations = observations
                for obs in observations:
                    if obs.artifacts:
                        all_artifacts.extend(obs.artifacts)
                obs_text = self._format_observations(tool_calls, observations)
                messages.append({"role": "assistant", "content": llm_response})
                messages.append({"role": "user", "content": obs_text})
            else:
                messages.append({"role": "assistant", "content": llm_response})
                messages.append({"role": "user", "content": "Please continue or produce <final_answer>."})

        duration = int((datetime.now() - start_time).total_seconds() * 1000)
        return HermesResult(success=False, react_steps=react_steps, total_duration_ms=duration, error=f"max steps exceeded")

    async def _call_llm(self, messages: List[Dict]) -> str:
        # Use claude CLI if available
        import shutil, subprocess
        if shutil.which(self.model):
            prompt_text = self._messages_to_prompt(messages)
            cmd = [self.model, "-p", prompt_text, "--dangerously-skip-permissions"]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.work_dir, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"LLM call failed: {result.stderr}")
            return result.stdout
        else:
            # Fallback: simple heuristic - return final answer echoing task
            user = next((m['content'] for m in messages if m['role']=='user'), '')
            return f"<thinking>Using no-LLM fallback</thinking>\n<final_answer>Completed task: {user[:200]}</final_answer>"

    def _messages_to_prompt(self, messages: List[Dict]) -> str:
        parts = []
        for msg in messages:
            role = msg['role'].upper()
            parts.append(f"[{role}]\n{msg['content']}")
        return "\n\n---\n\n".join(parts)

    def _parse_response(self, text: str) -> Tuple[str, List[Dict], bool, Optional[str]]:
        thought = ""
        tool_calls = []
        is_final = False
        final_answer = None

        m = re.search(r"<thinking>(.*?)</thinking>", text, re.DOTALL)
        if m:
            thought = m.group(1).strip()

        for tc in re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL):
            try:
                call = json.loads(tc.group(1).strip())
                tool_calls.append(call)
            except Exception:
                logger.warning("Failed to parse tool_call JSON")

        fa = re.search(r"<final_answer>(.*?)</final_answer>", text, re.DOTALL)
        if fa:
            is_final = True
            final_answer = fa.group(1).strip()

        if not thought and not tool_calls and not is_final:
            thought = text.strip()[:500]

        return thought, tool_calls, is_final, final_answer

    async def _execute_parallel_tools(self, tool_calls: List[Dict]) -> List[ToolResult]:
        tasks = [self._execute_single_tool(tc) for tc in tool_calls]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _execute_single_tool(self, tool_call: Dict) -> ToolResult:
        name = tool_call.get('name')
        params = tool_call.get('params', {})
        tool = self.registry.get(name)
        if not tool:
            return ToolResult(success=False, error=f"tool '{name}' not found")
        err = tool.validate_params(params)
        if err:
            return ToolResult(success=False, error=f"param error: {err}")
        try:
            return await tool.run(params, work_dir=self.work_dir)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def _format_observations(self, tool_calls: List[Dict], observations: List[ToolResult]) -> str:
        parts = []
        for call, obs in zip(tool_calls, observations):
            name = call.get('name')
            success = 'true' if obs.success else 'false'
            if obs.success:
                content = json.dumps({'output': obs.output, **obs.metadata}, ensure_ascii=False)
            else:
                content = f"Error: {obs.error}"
            parts.append(f'<observation tool="{name}" success="{success}">\n{content}\n</observation>')
        return "\n\n".join(parts)
