"""
render_marp.py
Marp CLI を使って Markdown を PDF/HTML/PPTX に変換する軽量実装。
出力は JSON を stdout にプリントして終了コードを返す。
"""

import argparse
import subprocess
import shutil
import json
from pathlib import Path
import sys

SUPPORTED_FORMATS = ("pdf", "html", "pptx")


def check_marp_available() -> bool:
    return shutil.which("marp") is not None


def get_marp_version() -> str:
    try:
        res = subprocess.run(["marp", "--version"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def inject_marp_frontmatter(md_content: str, theme: str = "default", paginate: bool = True) -> str:
    if "marp: true" in md_content:
        return md_content
    front = f"---\nmarp: true\ntheme: {theme}\npaginate: {str(paginate).lower()}\n---\n\n"
    return front + md_content


def render_marp_slides(input_path: str, output_path: str, output_format: str = "pdf",
                       theme: str = None, allow_local_files: bool = True,
                       auto_inject_frontmatter: bool = True) -> dict:
    start = None
    try:
        if output_format not in SUPPORTED_FORMATS:
            return {"success": False, "error": f"unsupported format: {output_format}", "output_path": output_path}

        if not check_marp_available():
            return {
                "success": False,
                "error": "marp command not found. Install: npm install -g @marp-team/marp-cli",
                "output_path": output_path
            }

        inp = Path(input_path)
        if not inp.exists():
            return {"success": False, "error": f"input not found: {input_path}", "output_path": output_path}

        actual_input = inp
        if auto_inject_frontmatter:
            content = inp.read_text(encoding="utf-8")
            if "marp: true" not in content:
                injected = inject_marp_frontmatter(content, theme or "default", paginate=True)
                tmp = inp.with_suffix(inp.suffix + ".marp_tmp.md")
                tmp.write_text(injected, encoding="utf-8")
                actual_input = tmp

        cmd = ["marp", str(actual_input), "-o", str(output_path)]
        if allow_local_files:
            cmd.append("--allow-local-files")
        if theme:
            cmd.extend(["--theme", theme])
        if output_format == "pdf":
            cmd.append("--pdf")
        elif output_format == "html":
            cmd.append("--html")
        elif output_format == "pptx":
            cmd.append("--pptx")

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # cleanup tmp
        if actual_input != inp and actual_input.exists():
            try:
                actual_input.unlink()
            except Exception:
                pass

        success = (res.returncode == 0)
        size = Path(output_path).stat().st_size if success and Path(output_path).exists() else 0
        marp_version = get_marp_version()

        return {
            "success": success,
            "output_path": output_path if success else None,
            "format": output_format,
            "size_bytes": size,
            "error": None if success else (res.stderr or res.stdout or "marp failed"),
            "marp_version": marp_version
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Marp rendering timed out (120s)", "output_path": output_path}
    except Exception as e:
        return {"success": False, "error": str(e), "output_path": output_path}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--format", default="pdf", choices=SUPPORTED_FORMATS)
    parser.add_argument("--theme", default=None)
    parser.add_argument("--allow-local-files", action="store_true")
    parser.add_argument("--no-allow-local-files", dest="allow_local_files", action="store_false")
    parser.add_argument("--auto-inject-frontmatter", dest="auto_inject_frontmatter", action="store_true")
    parser.add_argument("--no-auto-inject-frontmatter", dest="auto_inject_frontmatter", action="store_false")
    parser.set_defaults(allow_local_files=True, auto_inject_frontmatter=True)
    args = parser.parse_args()

    result = render_marp_slides(
        args.input, args.output, args.format, theme=args.theme,
        allow_local_files=args.allow_local_files,
        auto_inject_frontmatter=args.auto_inject_frontmatter
    )

    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("success") else 1
)
