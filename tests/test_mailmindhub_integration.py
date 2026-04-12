#!/usr/bin/env python3
"""
MailMindHub ↔ harness 联动测试

测试场景：
1. 健康检查
2. 从邮件创建任务（有效命令）
3. 从邮件创建任务（无效命令/帮助）
4. 查询任务状态
5. Webhook 回调测试
6. 完整流程模拟（创建 → 轮询 → 完成）
"""

import sys
import time
import json
import requests
from pathlib import Path

# 配置
HARNESS_API_URL = "http://localhost:7500"
API_TOKEN = ""  # 如果有设置 HARNESS_API_TOKEN，在这里填写

HEADERS = {"Content-Type": "application/json"}
if API_TOKEN:
    HEADERS["X-API-Key"] = API_TOKEN

def print_section(title):
    """打印分节标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_health_check():
    """测试 1: 健康检查"""
    print_section("测试 1: 健康检查")
    
    try:
        resp = requests.get(f"{HARNESS_API_URL}/api/v1/health", headers=HEADERS, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        print(f"✅ 健康检查通过")
        print(f"   状态: {data['status']}")
        print(f"   服务: {data['service']}")
        print(f"   版本: {data['version']}")
        return True
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        return False


def test_create_task_from_email_valid():
    """测试 2: 从邮件创建任务（有效命令）"""
    print_section("测试 2: 从邮件创建任务（有效命令：/generate）")
    
    payload = {
        "subject": "/generate 写一个快速排序函数",
        "body": "/generate 写一个快速排序函数，要求支持泛型类型",
        "from_addr": "test@example.com",
        "callback_url": "http://localhost:9999/test-callback"  # 测试用回调 URL
    }
    
    try:
        print(f"📧 模拟 MailMindHub 转发邮件...")
        print(f"   主题: {payload['subject']}")
        print(f"   正文: {payload['body']}")
        print(f"   发件人: {payload['from_addr']}")
        
        resp = requests.post(
            f"{HARNESS_API_URL}/api/v1/tasks/from-email",
            headers=HEADERS,
            json=payload,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        
        print(f"\n✅ 任务创建成功")
        print(f"   Task ID: {data['task_id']}")
        print(f"   状态: {data['status']}")
        print(f"   消息: {data['message']}")
        
        return data.get('task_id')
    except Exception as e:
        print(f"❌ 任务创建失败: {e}")
        return None


def test_create_task_from_email_invalid():
    """测试 3: 从邮件创建任务（无效命令）"""
    print_section("测试 3: 从邮件创建任务（无效命令）")
    
    payload = {
        "subject": "随便聊聊",
        "body": "今天天气怎么样？",
        "from_addr": "test@example.com"
    }
    
    try:
        print(f"📧 模拟无效邮件...")
        print(f"   主题: {payload['subject']}")
        print(f"   正文: {payload['body']}")
        
        resp = requests.post(
            f"{HARNESS_API_URL}/api/v1/tasks/from-email",
            headers=HEADERS,
            json=payload,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        
        print(f"\n✅ 无效命令处理正确")
        print(f"   状态: {data['status']}")
        print(f"   帮助已发送: {data['help_sent']}")
        print(f"   消息: {data['message']}")
        
        return True
    except Exception as e:
        print(f"❌ 处理失败: {e}")
        return False


def test_query_task_status(task_id):
    """测试 4: 查询任务状态"""
    print_section(f"测试 4: 查询任务状态 (ID: {task_id})")
    
    try:
        resp = requests.get(
            f"{HARNESS_API_URL}/api/v1/tasks/{task_id}",
            headers=HEADERS,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        
        print(f"✅ 任务状态查询成功")
        print(f"   标题: {data['title']}")
        print(f"   状态: {data['status']}")
        print(f"   来源: {data['source']}")
        print(f"   创建时间: {data['created_at']}")
        
        if data['runs']:
            print(f"\n   执行步骤:")
            for run in data['runs']:
                print(f"     - [{run['phase']}] {run['agent']}: {run['status']}")
        
        return data
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return None


def test_list_tasks():
    """测试 5: 查询任务列表"""
    print_section("测试 5: 查询任务列表")
    
    try:
        resp = requests.get(
            f"{HARNESS_API_URL}/api/v1/tasks?limit=5",
            headers=HEADERS,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        
        print(f"✅ 任务列表查询成功")
        print(f"   总数: {data['total']}")
        print(f"   返回: {len(data['tasks'])} 个任务")
        
        for task in data['tasks'][:3]:
            print(f"     - #{task['task_id']}: {task['title']} [{task['status']}]")
        
        return True
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return False


def test_list_agents():
    """测试 6: 查询可用 Agent"""
    print_section("测试 6: 查询可用 Agent 列表")
    
    try:
        resp = requests.get(
            f"{HARNESS_API_URL}/api/v1/agents",
            headers=HEADERS,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        
        print(f"✅ Agent 列表查询成功")
        print(f"   可用 Agent 数量: {len(data.get('agents', []))}")
        
        for agent in data.get('agents', []):
            print(f"     - {agent['name']} (角色: {agent['role']}, 命令: {agent['cli_command']})")
        
        return True
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return False


def test_poll_until_complete(task_id, max_wait=120):
    """测试 7: 轮询等待任务完成"""
    print_section(f"测试 7: 轮询等待任务完成 (ID: {task_id})")
    
    start_time = time.time()
    poll_interval = 5
    
    while time.time() - start_time < max_wait:
        try:
            resp = requests.get(
                f"{HARNESS_API_URL}/api/v1/tasks/{task_id}",
                headers=HEADERS,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            
            status = data['status']
            elapsed = int(time.time() - start_time)
            
            print(f"   ⏳ [{elapsed}s] 状态: {status}")
            
            if status in ('completed', 'failed'):
                print(f"\n{'✅' if status == 'completed' else '❌'} 任务结束")
                print(f"   最终状态: {status}")
                print(f"   结果: {data.get('result', 'N/A')[:200]}")
                
                if data['runs']:
                    print(f"\n   执行步骤:")
                    for run in data['runs']:
                        verdict = f" (评估: {run['eval_verdict']})" if run.get('eval_verdict') else ""
                        print(f"     - [{run['phase']}] {run['agent']}: {run['status']}{verdict}")
                
                return data
            
            time.sleep(poll_interval)
            
        except Exception as e:
            print(f"   ❌ 查询失败: {e}")
            return None
    
    print(f"   ⏰ 超时 ({max_wait}s)")
    return None


def test_create_task_generic():
    """测试 8: 创建通用任务（非邮件）"""
    print_section("测试 8: 创建通用任务（API 直接调用）")
    
    payload = {
        "title": "测试任务 - 排序算法",
        "prompt": "实现一个归并排序算法",
        "success_criteria": "1. 时间复杂度 O(n log n)\n2. 稳定排序",
        "pipeline_mode": True,
        "source": "test"
    }
    
    try:
        resp = requests.post(
            f"{HARNESS_API_URL}/api/v1/tasks",
            headers=HEADERS,
            json=payload,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        
        print(f"✅ 通用任务创建成功")
        print(f"   Task ID: {data['task_id']}")
        print(f"   状态: {data['status']}")
        print(f"   消息: {data['message']}")
        
        return data.get('task_id')
    except Exception as e:
        print(f"❌ 任务创建失败: {e}")
        return None


def print_summary(results):
    """打印测试总结"""
    print_section("测试总结")
    
    total = len(results)
    passed = sum(1 for r in results.values() if r)
    failed = total - passed
    
    print(f"\n总测试数: {total}")
    print(f"✅ 通过: {passed}")
    print(f"❌ 失败: {failed}")
    print(f"\n详细结果:")
    for test_name, result in results.items():
        status = "✅" if result else "❌"
        print(f"  {status} {test_name}")
    
    return failed == 0


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("  MailMindHub ↔ harness 联动测试")
    print("="*60)
    print(f"\n目标服务: {HARNESS_API_URL}")
    print(f"API Token: {'已设置' if API_TOKEN else '未设置（开发模式）'}")
    
    results = {}
    
    # 1. 健康检查
    results['健康检查'] = test_health_check()
    if not results['健康检查']:
        print("\n❌ harness API 不可达，请确认服务已启动")
        print(f"   启动命令: cd /home/ubuntu/ws/harness && python3 harness_api.py")
        return False
    
    # 2. 查询 Agent 列表
    results['Agent 列表'] = test_list_agents()
    
    # 3. 无效邮件命令处理
    results['无效邮件处理'] = test_create_task_from_email_invalid()
    
    # 4. 从邮件创建任务（有效命令）
    task_id_1 = test_create_task_from_email_valid()
    results['邮件任务创建'] = task_id_1 is not None
    
    # 5. 查询任务状态
    if task_id_1:
        task_data = test_query_task_status(task_id_1)
        results['任务状态查询'] = task_data is not None
        
        # 6. 轮询等待完成（可选，因为实际执行可能需要较长时间）
        print_section("测试 6: 轮询任务完成（最多等待 60 秒）")
        print("⚠️  实际 Pipeline 执行可能需要较长时间")
        print("   此处仅做短暂轮询演示")
        
        final_status = test_poll_until_complete(task_id_1, max_wait=60)
        results['任务轮询完成'] = final_status is not None and final_status['status'] in ('completed', 'failed')
    
    # 7. 创建通用任务
    task_id_2 = test_create_task_generic()
    results['通用任务创建'] = task_id_2 is not None
    
    # 8. 查询任务列表
    results['任务列表查询'] = test_list_tasks()
    
    # 打印总结
    all_passed = print_summary(results)
    
    print(f"\n{'='*60}")
    if all_passed:
        print("🎉 所有测试通过！MailMindHub 和 harness 联动正常")
    else:
        print("⚠️  部分测试失败，请检查日志和配置")
    print(f"{'='*60}\n")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
