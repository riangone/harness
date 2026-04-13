"""
browser_action.py
Playwright を使った簡易ブラウザ操作スクリプト（スクリーンショット等）
"""

import argparse
import json
import sys
from pathlib import Path


def screenshot(url: str, output_file: str, wait_ms: int = 1000) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return {"success": False, "error": f"playwright not available: {e}", "output_path": None}

    outp = Path(output_file)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url)
            page.wait_for_timeout(wait_ms)
            page.screenshot(path=str(outp), full_page=True)
            browser.close()
        size = outp.stat().st_size if outp.exists() else 0
        return {"success": True, "output_path": str(outp), "size_bytes": size}
    except Exception as e:
        return {"success": False, "error": str(e), "output_path": None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=["screenshot"])
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--wait-ms", type=int, default=1000)
    args = parser.parse_args()

    if args.action == "screenshot":
        res = screenshot(args.url, args.output, wait_ms=args.wait_ms)
        print(json.dumps(res, ensure_ascii=False))
        sys.exit(0 if res.get("success") else 1)

