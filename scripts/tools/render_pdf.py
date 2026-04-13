"""
render_pdf.py
Markdown/HTML を PDF に変換するスクリプト（weasyprint/pdfkit のどちらかを使用）
出力は JSON を stdout にプリントして終了コードを返す。
"""

import argparse
import json
import sys
from pathlib import Path


def render_md_or_html_to_pdf(input_path: str, output_path: str, engine: str = "weasyprint") -> dict:
    try:
        p = Path(input_path)
        if not p.exists():
            return {"success": False, "error": f"input not found: {input_path}", "output_path": None}

        content = p.read_text(encoding="utf-8") if p.suffix.lower() in (".md", ".html", ".htm") else None

        # If markdown, convert to HTML lazily
        if p.suffix.lower() == ".md":
            try:
                import markdown2
                html = markdown2.markdown(content)
            except Exception:
                # fallback: wrap in <pre>
                html = "<pre>" + content + "</pre>"
        else:
            html = content if content is not None else p.read_text(encoding="utf-8")

        outp = Path(output_path)

        if engine == "weasyprint":
            try:
                from weasyprint import HTML
                HTML(string=html).write_pdf(str(outp))
            except Exception as e:
                return {"success": False, "error": f"weasyprint error: {e}", "output_path": None}
        else:
            # pdfkit fallback
            try:
                import pdfkit
                pdfkit.from_string(html, str(outp))
            except Exception as e:
                return {"success": False, "error": f"pdfkit error: {e}", "output_path": None}

        size = outp.stat().st_size if outp.exists() else 0
        return {"success": True, "output_path": str(outp), "size_bytes": size}

    except Exception as e:
        return {"success": False, "error": str(e), "output_path": None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--engine", choices=["weasyprint", "pdfkit"], default="weasyprint")
    args = parser.parse_args()

    res = render_md_or_html_to_pdf(args.input, args.output, engine=args.engine)
    print(json.dumps(res, ensure_ascii=False))
    sys.exit(0 if res.get("success") else 1
)
