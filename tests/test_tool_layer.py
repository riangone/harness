import asyncio
import shutil
import json
from pathlib import Path
import pytest

from core.tools.registry import ToolRegistry
from core.tools.base import BaseTool, ToolResult
from core.pipeline.engine import PipelineEngine, StepResult
from core.pipeline.template import PipelineTemplate, PipelineStep


def test_tool_registry_get_schemas(tmp_path):
    registry = ToolRegistry.get_instance()

    # register a dummy tool for testing
    class DummyTool(BaseTool):
        name = "dummy_tool"
        description = "dummy"
        async def run(self, params, work_dir="."):
            return ToolResult(success=True, output="ok", artifacts=[])

    registry.register(DummyTool())
    schemas = registry.get_schemas_for_llm()
    assert isinstance(schemas, list)
    names = [s.get('name') for s in schemas]
    assert 'dummy_tool' in names


@pytest.mark.skipif(shutil.which('marp') is None, reason='marp not installed')
def test_marp_renderer_tool(tmp_path):
    from core.tools.renderers.marp import MarpRenderer
    tool = MarpRenderer()
    md = tmp_path / "slides.md"
    md.write_text("# Title\n\n---\n\n# Slide 2\n- Point 1\n")
    out = tmp_path / "slides.pdf"
    res = asyncio.run(tool.run({"input_file": str(md), "output_file": str(out), "format": "pdf"}, work_dir=str(tmp_path)))
    assert res.success
    assert out.exists() and out.stat().st_size > 0


def test_pipeline_tool_call_step(tmp_path):
    # Create a dummy tool that writes a file
    class FileTool(BaseTool):
        name = "file_tool"
        description = "writes a file"
        async def run(self, params, work_dir='.'):
            p = Path(work_dir) / params.get('output_file')
            p.write_text('ok')
            return ToolResult(success=True, output=str(p), artifacts=[str(p)])

    registry = ToolRegistry.get_instance()
    registry.register(FileTool())

    # build a pipeline template with a single tool_call step
    step = PipelineStep(id='render', type='tool_call', tool='file_tool', tool_params={
        'output_file': 'out.txt'
    })
    template = PipelineTemplate(name='test', steps=[step])

    engine = PipelineEngine()
    # execute with work_dir set in context
    result = asyncio.run(engine.execute(task_type='test', task_input='do it', template=template, context={'work_dir': str(tmp_path)}))
    assert result.step_results['render'].success
    outp = tmp_path / 'out.txt'
    assert outp.exists()
