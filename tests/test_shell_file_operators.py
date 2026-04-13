import asyncio
import sys
from pathlib import Path
import pytest

from core.tools.operators.shell import ShellExecutor
from core.tools.operators.file import FileOperator
from core.tools.base import ToolResult


def test_shell_requires_approval(tmp_path):
    tool = ShellExecutor()
    # use python executable to avoid shell-specific commands
    params = {"command": sys.executable, "args": ["-c", "print('no')"], "approved": False}
    res = asyncio.run(tool.run(params, work_dir=str(tmp_path)))
    assert res.success is False
    assert 'approval' in (res.error or '').lower()


def test_shell_exec_with_approval(tmp_path):
    tool = ShellExecutor()
    params = {"command": sys.executable, "args": ["-c", "print('hello')"], "approved": True}
    res = asyncio.run(tool.run(params, work_dir=str(tmp_path)))
    assert res.success is True
    assert 'hello' in (res.output or '')


def test_file_operator_write_read_list(tmp_path):
    tool = FileOperator()
    # write
    write_params = {"action": "write", "path": "subdir/test.txt", "content": "abc123"}
    wr = asyncio.run(tool.run(write_params, work_dir=str(tmp_path)))
    assert wr.success
    out_path = tmp_path / "subdir" / "test.txt"
    assert out_path.exists()

    # list
    list_params = {"action": "list", "path": "subdir"}
    lr = asyncio.run(tool.run(list_params, work_dir=str(tmp_path)))
    assert lr.success
    assert 'test.txt' in lr.output

    # read
    read_params = {"action": "read", "path": "subdir/test.txt"}
    rr = asyncio.run(tool.run(read_params, work_dir=str(tmp_path)))
    assert rr.success
    assert 'abc123' in rr.output
