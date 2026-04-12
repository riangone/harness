#!/usr/bin/env python3
"""
MailMindHub ↔ harness 快速联动测试

测试核心功能：
1. 健康检查
2. 邮件任务创建
3. 任务状态查询
"""

import sys
import requests

HARNESS_API_URL = "http://localhost:7500"
HEADERS = {"Content-Type": "application/json"}

def main():
    print("\n" + "="*60)
    print("  MailMindHub ↔ harness 快速联动测试")
    print("="*60 + "\n")
    
    # 测试 1: 健康检查
    print("1️⃣  健康检查...")
    resp = requests.get(f"{HARNESS_API_URL}/api/v1/health", headers=HEADERS, timeout=5)
    health = resp.json()
    print(f"   ✅ {health['status']} - {health['service']} v{health['version']}\n")
    
    # 测试 2: 从邮件创建任务（/generate 命令）
    print("2️⃣  模拟 MailMindHub 转发邮件...")
    email_payload = {
        "subject": "/generate 写一个冒泡排序",
        "body": "/generate 请用 Python 实现一个冒泡排序函数，包含类型注解和文档字符串",
        "from_addr": "user@example.com"
    }
    
    resp = requests.post(
        f"{HARNESS_API_URL}/api/v1/tasks/from-email",
        headers=HEADERS,
        json=email_payload,
        timeout=10
    )
    task_data = resp.json()
    
    if task_data.get('task_id'):
        task_id = task_data['task_id']
        print(f"   ✅ 任务创建成功")
        print(f"      Task ID: {task_id}")
        print(f"      Pipeline: {task_data['message'].split(': ')[-1] if ':' in task_data['message'] else 'N/A'}\n")
        
        # 测试 3: 查询任务状态
        print("3️⃣  查询任务状态...")
        resp = requests.get(f"{HARNESS_API_URL}/api/v1/tasks/{task_id}", headers=HEADERS, timeout=10)
        status_data = resp.json()
        
        print(f"   ✅ 状态: {status_data['status']}")
        print(f"      标题: {status_data['title']}")
        print(f"      来源: {status_data['source']}")
        
        if status_data.get('runs'):
            print(f"\n   执行步骤:")
            for run in status_data['runs']:
                print(f"     - [{run['phase']}] {run['agent']}: {run['status']}")
        
        print("\n" + "="*60)
        print("✅ 快速测试完成！MailMindHub 和 harness 联动正常")
        print("="*60 + "\n")
        return True
    else:
        print(f"   ❌ 任务创建失败: {task_data['message']}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
