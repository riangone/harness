"""
tool_runner.py — 統合ツールランナー（簡易実装）
指定したツールを呼び出すシンプルなエントリーポイント。
現時点では marp のラップをサポートする。
"""

import argparse
import subprocess
import sys
import json
from pathlib import Path

TOOLS_DIR = Path(__file__).parent
RENDER_MARP = TOOLS_DIR / "render_marp.py"


def run_marp(args) -> int:
    cmd = [sys.executable, str(RENDER_MARP), "--input", args.input, "--output", args.output, "--format", args.format]
    if args.theme:
        cmd.extend(["--theme", args.theme])
    if args.allow_local_files is False:
        cmd.append("--no-allow-local-files")
    if args.auto_inject_frontmatter is False:
        cmd.append("--no-auto-inject-frontmatter")

    res = subprocess.run(cmd, capture_output=True, text=True)
    # forward stdout/stderr
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)
    return res.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True)
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--format", default="pdf")
    parser.add_argument("--theme", default=None)
    parser.add_argument("--allow-local-files", dest="allow_local_files", action="store_true")
    parser.add_argument("--no-allow-local-files", dest="allow_local_files", action="store_false")
    parser.add_argument("--auto-inject-frontmatter", dest="auto_inject_frontmatter", action="store_true")
    parser.add_argument("--no-auto-inject-frontmatter", dest="auto_inject_frontmatter", action="store_false")
    parser.set_defaults(allow_local_files=True, auto_inject_frontmatter=True)
    args = parser.parse_args()

    if args.tool == "marp":
        returncode = run_marp(args)
        sys.exit(returncode)
    else:
        print(json.dumps({"success": False, "error": f"unsupported tool: {args.tool}"}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
