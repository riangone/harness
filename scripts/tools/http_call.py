"""
http_call.py
外部 REST API を呼び出す簡易スクリプト（requests を使用）
"""

import argparse
import json
import sys
from pathlib import Path


def http_call(method: str, url: str, body: str = "", headers: str = "{}", timeout: int = 30) -> dict:
    try:
        import requests
    except Exception as e:
        return {"success": False, "error": f"requests not available: {e}", "output": None}

    try:
        hdrs = json.loads(headers) if headers else {}
        data = json.loads(body) if body else None
    except Exception as e:
        return {"success": False, "error": f"invalid json for headers/body: {e}", "output": None}

    try:
        resp = requests.request(method, url, json=data, headers=hdrs, timeout=timeout)
        return {"success": True, "status_code": resp.status_code, "output": resp.text}
    except Exception as e:
        return {"success": False, "error": str(e), "output": None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--body", default="")
    parser.add_argument("--headers", default="{}")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    res = http_call(args.method, args.url, body=args.body, headers=args.headers, timeout=args.timeout)
    print(json.dumps(res, ensure_ascii=False))
    sys.exit(0 if res.get("success") else 1)
