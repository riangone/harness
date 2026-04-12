#!/usr/bin/env python3
"""
harness_wrapper.py - NetYamlForge 调用 Harness pipeline_executor 的包装脚本

用法:
    python3 harness_wrapper.py --prompt "任务描述" --work-dir /path/to/work [--project 项目名] [--timeout 3600]
"""

import sys
import os
import json
import argparse
from datetime import datetime

# 添加 webui/app 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.pipeline_executor import run_pipeline

def main():
    parser = argparse.ArgumentParser(description='Harness Pipeline Wrapper for NetYamlForge')
    parser.add_argument('--prompt', required=True, help='任务描述')
    parser.add_argument('--work-dir', required=True, help='工作目录')
    parser.add_argument('--project', help='项目名称')
    parser.add_argument('--timeout', type=int, help='超时秒数')
    parser.add_argument('--json', action='store_true', help='JSON 输出模式')
    
    args = parser.parse_args()
    
    try:
        result = run_pipeline(
            prompt=args.prompt,
            work_dir=args.work_dir,
            pipeline_mode="full",
            project_name=args.project,
            timeout=args.timeout
        )
        
        if args.json:
            # JSON 输出（供 .NET 程序解析）
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            # 人类可读输出
            print(f"状态: {result['status']}")
            print(f"工作目录: {result['work_dir']}")
            if result.get('task_id'):
                print(f"任务 ID: {result['task_id']}")
            print(f"\n输出:\n{result['output']}")
        
        # 退出码
        sys.exit(0 if result['status'] == 'completed' else 1)
        
    except Exception as e:
        error_result = {
            'status': 'failed',
            'error': str(e),
            'work_dir': args.work_dir
        }
        
        if args.json:
            print(json.dumps(error_result, ensure_ascii=False, indent=2))
        else:
            print(f"[错误] {str(e)}", file=sys.stderr)
        
        sys.exit(1)

if __name__ == '__main__':
    main()
