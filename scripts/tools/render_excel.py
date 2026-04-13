"""
render_excel.py
JSON/CSV を Excel (.xlsx) に変換する簡易実装（openpyxl が必要）
"""

import argparse
import json
import sys
from pathlib import Path


def render_json_to_excel(input_path: str, output_path: str, title: str = "") -> dict:
    try:
        from openpyxl import Workbook
    except Exception as e:
        return {"success": False, "error": f"openpyxl not available: {e}", "output_path": None}

    p = Path(input_path)
    if not p.exists():
        return {"success": False, "error": f"input not found: {input_path}", "output_path": None}

    data = json.loads(p.read_text(encoding="utf-8")) if p.suffix.lower() == ".json" else None
    wb = Workbook()
    wb.remove(wb.active)

    if data is None:
        return {"success": False, "error": "unsupported input format (only .json supported)", "output_path": None}

    for sheet in data.get("sheets", []):
        ws = wb.create_sheet(title=sheet.get("name", "Sheet"))
        headers = sheet.get("headers", [])
        if headers:
            ws.append(headers)
        for row in sheet.get("rows", []):
            ws.append(row)

    outp = Path(output_path)
    wb.save(str(outp))
    size = outp.stat().st_size if outp.exists() else 0
    return {"success": True, "output_path": str(outp), "size_bytes": size}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default="")
    args = parser.parse_args()

    res = render_json_to_excel(args.input, args.output, title=args.title)
    print(json.dumps(res, ensure_ascii=False))
    sys.exit(0 if res.get("success") else 1)
