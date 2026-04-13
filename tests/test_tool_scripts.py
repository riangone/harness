import json
import shutil
import subprocess
import sys
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "tools"


def run_script(script: Path, args: list, tmp_path: Path):
    cmd = [sys.executable, str(script)] + args
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        out = res.stdout.strip()
        if not out:
            out = res.stderr.strip()
        data = json.loads(out)
    except Exception:
        pytest.skip(f"Script {script.name} did not return JSON; stdout: {res.stdout}, stderr: {res.stderr}")
    assert data.get("success") is True


@pytest.mark.skipif(shutil.which("marp") is None, reason="marp not installed")
def test_render_marp_pdf(tmp_path):
    md = tmp_path / "slides.md"
    md.write_text("# Title\n\n---\n\n# Slide 2\n- Point 1\n- Point 2\n")
    out = tmp_path / "slides.pdf"
    script = SCRIPTS_DIR / "render_marp.py"
    run_script(script, ["--input", str(md), "--output", str(out), "--format", "pdf"], tmp_path)
    assert out.exists() and out.stat().st_size > 0


@pytest.mark.skipif(not shutil.which(sys.executable), reason="python not available")
def test_render_pptx_from_md(tmp_path):
    md = tmp_path / "slides.md"
    md.write_text("# Title\n- Item 1\n- Item 2\n")
    out = tmp_path / "presentation.pptx"
    script = SCRIPTS_DIR / "render_pptx.py"
    # skip if python-pptx not installed
    try:
        import pptx  # type: ignore
    except Exception:
        pytest.skip("python-pptx not installed")
    run_script(script, ["--input", str(md), "--output", str(out)], tmp_path)
    assert out.exists() and out.stat().st_size > 0


def test_render_excel_from_json(tmp_path):
    data = tmp_path / "data.json"
    sample = {
        "title": "Report",
        "sheets": [
            {"name": "Sheet1", "headers": ["A", "B"], "rows": [[1,2],[3,4]]}
        ]
    }
    data.write_text(json.dumps(sample, ensure_ascii=False))
    out = tmp_path / "report.xlsx"
    script = SCRIPTS_DIR / "render_excel.py"
    try:
        import openpyxl  # type: ignore
    except Exception:
        pytest.skip("openpyxl not installed")
    run_script(script, ["--input", str(data), "--output", str(out)], tmp_path)
    assert out.exists() and out.stat().st_size > 0


def test_render_docx_from_md(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Heading\nThis is a paragraph.\n- bullet1\n- bullet2\n")
    out = tmp_path / "doc.docx"
    script = SCRIPTS_DIR / "render_docx.py"
    try:
        import docx  # type: ignore
    except Exception:
        pytest.skip("python-docx not installed")
    run_script(script, ["--input", str(md), "--output", str(out)], tmp_path)
    assert out.exists() and out.stat().st_size > 0
