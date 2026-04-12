#!/usr/bin/env python
"""
Harness 2.0 核心模块测试

测试：
1. ModelRegistry - 模型选择和路由
2. MemoryService - 记忆存储和检索
3. PipelineEngine - Pipeline执行
4. MailGateway - 邮件解析和路由
"""

import asyncio
import os
import sys
import tempfile
import json
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_model_registry():
    """测试模型注册表"""
    print("\n" + "="*60)
    print("测试 1: ModelRegistry")
    print("="*60)
    
    from core.models.registry import ModelRegistry
    
    # 使用测试配置
    test_config = {
        'providers': {
            'cli': {
                'models': [
                    {
                        'id': 'claude',
                        'roles': ['planner', 'evaluator'],
                        'cost_per_1k': 0.015,
                        'quality_score': 0.98,
                        'context_window': 200000,
                        'cli_command': 'claude'
                    },
                    {
                        'id': 'qwen',
                        'roles': ['generator', 'bug_fixer'],
                        'cost_per_1k': 0.002,
                        'quality_score': 0.85,
                        'context_window': 32768,
                        'cli_command': 'qwen'
                    }
                ]
            }
        },
        'routing': {
            'default_strategy': 'cost_aware',
            'fallback_chain': [{'try': ['qwen']}]
        }
    }
    
    # 写入临时配置
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        import yaml
        yaml.dump(test_config, f)
        config_path = f.name
    
    try:
        registry = ModelRegistry(config_path)
        
        # 测试1: 获取所有模型
        all_models = registry.get_all_models()
        print(f"✅ 注册的模型数量: {len(all_models)}")
        assert len(all_models) == 2, f"Expected 2 models, got {len(all_models)}"
        
        # 测试2: 按角色过滤
        generator_models = registry.get_models_for_role('generator')
        print(f"✅ Generator角色可用模型: {len(generator_models)}")
        assert len(generator_models) == 1
        
        # 测试3: 选择模型（成本优先）
        selected = registry.select('generator', {'strategy': 'cost_aware'})
        print(f"✅ 选择的模型: {selected.id} (cost={selected.cost_per_1k})")
        assert selected.id == 'qwen'
        
        # 测试4: 选择模型（质量优先）
        selected_quality = registry.select('planner', {'strategy': 'quality_first'})
        print(f"✅ Planner角色选择: {selected_quality.id} (quality={selected_quality.quality_score})")
        assert selected_quality.id == 'claude'
        
        print("\n✅ ModelRegistry 测试通过!")
        
    finally:
        os.unlink(config_path)


def test_memory_service():
    """测试记忆服务"""
    print("\n" + "="*60)
    print("测试 2: MemoryService")
    print("="*60)
    
    from core.memory.service import MemoryService
    
    # 使用临时数据库
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        memory = MemoryService(db_path)
        
        # 测试1: 存储成功经验
        exp_id = memory.store_experience(
            task_type='code_generation',
            outcome='success',
            data={
                'template': '使用函数式编程风格',
                'metrics': {'duration': 5000},
                'tags': ['python', 'functional']
            },
            agent_role='generator',
            retention_days=30
        )
        print(f"✅ 存储经验ID: {exp_id}")
        assert exp_id > 0
        
        # 测试2: 存储失败经验
        fail_id = memory.store_experience(
            task_type='code_generation',
            outcome='failed',
            data={
                'lesson': '避免使用全局变量',
                'patterns': ['global_state_mutation'],
                'tags': ['python', 'best_practice']
            },
            agent_role='generator',
            retention_days=30
        )
        print(f"✅ 存储失败经验ID: {fail_id}")
        assert fail_id > 0
        
        # 测试3: 检索相似记忆（包括所有结果）
        similar = memory.retrieve_similar('code_generation', limit=5, outcome_filter=None)
        print(f"✅ 检索到相似记忆: {len(similar)} 条")
        assert len(similar) == 2, f"Expected 2 memories, got {len(similar)}"
        
        # 测试4: 构建上下文
        context = memory.build_context_from_memories(similar)
        print(f"✅ 构建上下文长度: {len(context)} 字符")
        assert len(context) > 0
        assert '历史经验参考' in context
        
        # 测试5: 统计信息
        stats = memory.get_statistics()
        print(f"✅ 记忆统计: 总数={stats['total']}, 成功={stats['success']}, 失败={stats['failed']}")
        assert stats['total'] == 2
        assert stats['success'] == 1
        assert stats['failed'] == 1
        
        print("\n✅ MemoryService 测试通过!")
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_mail_gateway():
    """测试邮件网关"""
    print("\n" + "="*60)
    print("测试 3: MailGateway")
    print("="*60)
    
    from core.gateway.mail import MailGateway

    # 使用默认配置（不加载配置文件）
    gateway = MailGateway.__new__(MailGateway)
    gateway.config = gateway._default_config()
    gateway.rules = gateway._parse_rules()
    gateway.response_template = gateway._load_template()

    # 测试1: 匹配路由规则
    rule = gateway.match_routing_rule("/generate 写一个排序函数", "/generate 写一个排序函数")
    print(f"✅ 匹配路由规则: action={rule.action}, pipeline={rule.pipeline}")
    assert rule.action == 'create_task'
    assert rule.pipeline == 'code_generation'
    
    # 测试2: 解析邮件为任务
    task = gateway.parse_email_to_task(
        subject="/generate test",
        body="/generate 写一个快速排序",
        from_addr="test@example.com"
    )
    print(f"✅ 解析任务: pipeline={task['pipeline']}, source={task['source']}")
    assert task['pipeline'] == 'code_generation'
    assert task['source'] == 'email'
    
    # 测试3: 帮助回复
    help_reply = gateway.generate_help_reply()
    print(f"✅ 帮助回复长度: {len(help_reply)} 字符")
    assert len(help_reply) > 50
    
    # 测试4: 格式化响应
    response = gateway.format_task_complete_response(
        task={'id': '123', 'input': 'test task'},
        result={
            'success': True,
            'duration_ms': 5000,
            'step_results': {'step1': {'success': True, 'model_used': 'qwen'}}
        }
    )
    print(f"✅ 响应邮件: subject={response['subject']}")
    assert '123' in response['subject']
    
    # 测试5: 网关统计
    stats = gateway.get_stats()
    print(f"✅ 网关统计: rules={stats['rules_count']}, pipelines={stats['pipelines']}")
    assert stats['rules_count'] > 0

    print("\n✅ MailGateway 测试通过!")


def test_pipeline_template():
    """测试Pipeline模板"""
    print("\n" + "="*60)
    print("测试 4: PipelineTemplate")
    print("="*60)
    
    from core.pipeline.template import TemplateLoader
    
    # 加载templates目录的模板
    loader = TemplateLoader("templates")
    
    # 测试1: 列出模板
    templates = loader.list_templates()
    print(f"✅ 加载模板数量: {len(templates)}")
    assert len(templates) > 0
    
    for t in templates:
        print(f"   - {t.name} v{t.version}: {t.description}")
    
    # 测试2: 匹配模板
    matched = loader.match('code_generation')
    if matched:
        print(f"✅ 匹配模板: {matched.name}")
        assert matched.name == 'code_generation'
    
    # 测试3: 获取默认模板
    default = loader.get_default()
    if default:
        print(f"✅ 默认模板: {default.name}")
        assert default.name == 'default_pipeline'
    
    print("\n✅ PipelineTemplate 测试通过!")


def test_pipeline_engine():
    """测试Pipeline引擎"""
    print("\n" + "="*60)
    print("测试 5: PipelineEngine")
    print("="*60)
    
    from core.pipeline.engine import PipelineEngine
    from core.models.registry import ModelRegistry
    from core.memory.service import MemoryService
    
    # 使用临时数据库
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        registry = ModelRegistry()
        memory = MemoryService(db_path)
        engine = PipelineEngine(
            registry=registry,
            memory=memory,
            template_dir="templates"
        )
        
        # 设置占位执行器
        async def mock_executor(step, model, prompt):
            return {"status": "mock_success", "output": "mocked"}
        
        engine.set_step_executor(mock_executor)
        
        # 测试：执行默认Pipeline
        async def run_test():
            result = await engine.execute(
                task_type='default',
                task_input='测试任务',
                session_id='test_session_001'
            )
            
            print(f"✅ Pipeline执行结果:")
            print(f"   - 模板: {result.template_name}")
            print(f"   - 成功: {result.success}")
            print(f"   - 耗时: {result.total_duration_ms}ms")
            print(f"   - 步骤数: {len(result.step_results)}")
            
            return result
        
        result = asyncio.run(run_test())
        
        assert result.template_name == 'default_pipeline'
        assert result.success is True
        
        print("\n✅ PipelineEngine 测试通过!")
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_orchestrator():
    """测试主编排器"""
    print("\n" + "="*60)
    print("测试 6: HarnessOrchestrator")
    print("="*60)
    
    from core.orchestrator import HarnessOrchestrator
    
    orchestrator = HarnessOrchestrator("config")
    
    # 测试1: 获取系统信息
    info = orchestrator.get_system_info()
    print(f"✅ 系统信息:")
    print(f"   - 模板数: {info['templates']}")
    print(f"   - 模型数: {info['models']}")
    
    # 测试2: 列出模板
    templates = orchestrator.list_templates()
    print(f"✅ 可用模板: {[t['name'] for t in templates]}")
    
    # 测试3: 列出模型
    models = orchestrator.list_models()
    print(f"✅ 可用模型: {[m['id'] for m in models]}")
    
    # 测试4: 运行任务（Mock）
    async def run_task_test():
        # 设置Mock执行器
        async def mock_executor(step, model, prompt):
            return {"status": "success", "output": "mocked_result"}
        
        orchestrator.set_step_executor(mock_executor)
        
        result = await orchestrator.run_task(
            task_type='default',
            task_input='测试输入'
        )
        
        print(f"✅ 任务执行结果: {'SUCCESS' if result['success'] else 'FAILED'}")
        return result
    
    result = asyncio.run(run_task_test())
    assert result['success'] is True
    
    print("\n✅ HarnessOrchestrator 测试通过!")


def main():
    """运行所有测试"""
    print("\n" + "🚀" * 30)
    print("Harness 2.0 核心模块测试")
    print("🚀" * 30)
    
    tests = [
        ("ModelRegistry", test_model_registry),
        ("MemoryService", test_memory_service),
        ("MailGateway", test_mail_gateway),
        ("PipelineTemplate", test_pipeline_template),
        ("PipelineEngine", test_pipeline_engine),
        ("HarnessOrchestrator", test_orchestrator)
    ]
    
    passed = 0
    failed = 0
    errors = []
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"\n❌ {name} 测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 总结
    print("\n" + "="*60)
    print(f"测试总结: {passed} 通过, {failed} 失败")
    print("="*60)
    
    if errors:
        print("\n失败详情:")
        for name, error in errors:
            print(f"  ❌ {name}: {error}")
    
    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
