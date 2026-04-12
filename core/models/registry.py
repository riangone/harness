"""
Model Registry - 模型注册表和智能选择器

提供统一的模型抽象层，支持：
- 配置驱动的模型定义（YAML）
- 基于角色/成本/质量的智能选择
- 自动fallback链
- 可用性检查
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
import yaml
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class ModelSpec:
    """模型规格定义"""
    id: str
    roles: List[str]
    cost_per_1k: float
    quality_score: float
    context_window: int
    provider: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    cli_command: Optional[str] = None  # 兼容现有CLI模式


class ModelRegistry:
    """
    模型注册表
    
    从YAML配置加载模型定义，提供智能选择策略：
    - cost_aware: 成本优先
    - quality_first: 质量优先
    - balanced: 平衡模式
    """
    
    def __init__(self, config_path: str = "config/models.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self._models: List[ModelSpec] = self._parse_models()
        self._availability_cache: Dict[str, bool] = {}

    def _load_config(self) -> Dict:
        """加载YAML配置"""
        if not os.path.exists(self.config_path):
            logger.warning(f"Config file not found: {self.config_path}, using defaults")
            return self._default_config()
        
        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def _default_config(self) -> Dict:
        """默认配置（当配置文件不存在时）"""
        return {
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
                        },
                        {
                            'id': 'gemini',
                            'roles': ['generator', 'researcher'],
                            'cost_per_1k': 0.003,
                            'quality_score': 0.88,
                            'context_window': 1000000,
                            'cli_command': 'gemini'
                        },
                        {
                            'id': 'codex',
                            'roles': ['generator'],
                            'cost_per_1k': 0.005,
                            'quality_score': 0.90,
                            'context_window': 8192,
                            'cli_command': 'codex'
                        }
                    ]
                }
            },
            'routing': {
                'default_strategy': 'cost_aware',
                'fallback_chain': [
                    {'try': ['claude', 'qwen']},
                    {'try': ['gemini']}
                ]
            }
        }

    def _parse_models(self) -> List[ModelSpec]:
        """解析配置中的模型定义"""
        models = []
        
        for provider_name, provider_cfg in self.config.get('providers', {}).items():
            for model_cfg in provider_cfg.get('models', []):
                api_key_env = provider_cfg.get('api_key_env')
                api_key = os.environ.get(api_key_env) if api_key_env else None
                
                model = ModelSpec(
                    id=model_cfg['id'],
                    roles=model_cfg.get('roles', []),
                    cost_per_1k=model_cfg.get('cost_per_1k', 0),
                    quality_score=model_cfg.get('quality_score', 0.5),
                    context_window=model_cfg.get('context_window', 4096),
                    provider=provider_name,
                    base_url=provider_cfg.get('base_url'),
                    api_key=api_key,
                    cli_command=model_cfg.get('cli_command')
                )
                models.append(model)
        
        return models

    def select(self, role: str, context: Optional[Dict] = None) -> ModelSpec:
        """
        智能选择模型
        
        Args:
            role: 角色类型 (planner/generator/evaluator/researcher)
            context: 上下文信息 (strategy/budget等)
            
        Returns:
            ModelSpec: 选中的模型规格
        """
        context = context or {}
        strategy = context.get(
            'strategy',
            self.config.get('routing', {}).get('default_strategy', 'balanced')
        )
        
        candidates = self._filter_by_role(role)
        if not candidates:
            raise ValueError(f"No models found for role: {role}")

        # 按策略排序
        if strategy == 'cost_aware':
            candidates.sort(key=lambda m: m.cost_per_1k)
        elif strategy == 'quality_first':
            candidates.sort(key=lambda m: m.quality_score, reverse=True)
        else:  # balanced - 性价比
            candidates.sort(
                key=lambda m: m.quality_score / max(m.cost_per_1k, 0.001),
                reverse=True
            )

        # 预算过滤
        if context.get('budget'):
            candidates = [
                m for m in candidates
                if m.cost_per_1k <= context['budget']
            ]
            if not candidates:
                candidates = self._filter_by_role(role)  # 重置

        # 按可用性检查
        for model in candidates:
            if self._check_availability(model):
                return model

        # fallback链
        return self._try_fallback(role)

    def _filter_by_role(self, role: str) -> List[ModelSpec]:
        """按角色过滤模型"""
        return [m for m in self._models if role in m.roles]

    def _check_availability(self, model: ModelSpec) -> bool:
        """检查模型可用性"""
        if model.id in self._availability_cache:
            return self._availability_cache[model.id]
        
        # CLI模式：检查命令是否存在
        if model.cli_command:
            import shutil
            available = shutil.which(model.cli_command) is not None
            if not available:
                logger.warning(f"CLI command not found: {model.cli_command}")
        else:
            # API模式：检查API key
            available = bool(model.api_key)
        
        self._availability_cache[model.id] = available
        return available

    def _try_fallback(self, role: str) -> ModelSpec:
        """尝试fallback链"""
        fallback_chain = self.config.get('routing', {}).get('fallback_chain', [])
        
        for stage in fallback_chain:
            for model_id in stage.get('try', []):
                for model in self._filter_by_role(role):
                    if model.id == model_id and self._check_availability(model):
                        logger.info(f"Using fallback model: {model.id}")
                        return model
        
        # 最后返回任意可用模型
        candidates = self._filter_by_role(role)
        if candidates:
            logger.warning(f"Using first available model for role '{role}': {candidates[0].id}")
            return candidates[0]
            
        raise ValueError(f"No available models for role: {role}")

    def get_all_models(self) -> List[ModelSpec]:
        """获取所有注册的模型"""
        return self._models.copy()

    def get_models_for_role(self, role: str) -> List[ModelSpec]:
        """获取指定角色的所有模型"""
        return self._filter_by_role(role)

    def reload(self):
        """重新加载配置"""
        self.config = self._load_config()
        self._models = self._parse_models()
        self._availability_cache.clear()
