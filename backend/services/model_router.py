"""
多模型智能路由 — Phase 3

根据任务复杂度、用户配额、模型可用性自动选择最优模型。
支持:
  - DeepSeek (默认, 最低成本)
  - Qwen (通义千问, 备选)
  - GPT-4o-mini (复杂推理)
  - GPT-4o (终极判决)
"""
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelConfig:
    name: str
    base_url: str
    cost_per_1k_tokens: float  # USD / 1K tokens
    max_context: int           # 最大上下文长度
    speed_tier: int            # 1=最快, 3=最慢
    capability_tier: int       # 1=基础, 3=最强
    is_available: bool = True
    last_check: float = 0.0
    error_count: int = 0


# ---- 模型注册表 ----
MODEL_REGISTRY: dict[str, ModelConfig] = {
    "deepseek-chat": ModelConfig(
        name="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        cost_per_1k_tokens=0.00014,
        max_context=64000,
        speed_tier=1,
        capability_tier=2,
    ),
    "qwen-plus": ModelConfig(
        name="qwen-plus",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        cost_per_1k_tokens=0.0008,
        max_context=128000,
        speed_tier=1,
        capability_tier=2,
    ),
    "gpt-4o-mini": ModelConfig(
        name="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        cost_per_1k_tokens=0.00015,
        max_context=128000,
        speed_tier=2,
        capability_tier=2,
    ),
    "gpt-4o": ModelConfig(
        name="gpt-4o",
        base_url="https://api.openai.com/v1",
        cost_per_1k_tokens=0.0025,
        max_context=128000,
        speed_tier=3,
        capability_tier=3,
    ),
}


class ModelRouter:
    """智能模型路由器"""

    def __init__(self, default_model: str = "deepseek-chat"):
        self.default_model = default_model
        self.registry = MODEL_REGISTRY.copy()

    def select_model(
        self,
        task_type: str = "general",
        input_tokens: int = 0,
        budget_remaining_usd: float = 999.0,
        prefer_speed: bool = False,
        prefer_quality: bool = False,
    ) -> ModelConfig:
        """
        智能选择模型

        策略:
          1. Manual Agent / Log Agent → 快速模型 (tier 1-2)
          2. Boss Agent → 综合最优 (tier 2-3)
          3. Code Agent → 中等 (tier 2)
          4. 预算不足 → 降级到最便宜
          5. 上下文超长 → 自动选支持长上下文的模型
        """
        available = {k: v for k, v in self.registry.items() if v.is_available}
        if not available:
            return self.registry.get(self.default_model, list(self.registry.values())[0])

        # 上下文长度过滤
        if input_tokens > 0:
            available = {k: v for k, v in available.items() if v.max_context >= input_tokens}
            if not available:
                # 所有模型都不够长，选最大的
                return max(self.registry.values(), key=lambda m: m.max_context)

        # 预算过滤 (估算: 至少够 4 次调用)
        if budget_remaining_usd < 0.01:
            return min(available.values(), key=lambda m: m.cost_per_1k_tokens)

        # 任务类型路由
        if task_type in ("manual", "log", "keyword"):
            # 快速任务 → 最便宜+最快
            candidates = sorted(
                available.values(),
                key=lambda m: (m.speed_tier, m.cost_per_1k_tokens),
            )
        elif task_type == "boss":
            # 综合判决 → 能力优先
            if prefer_quality:
                candidates = sorted(available.values(), key=lambda m: -m.capability_tier)
            else:
                candidates = sorted(
                    available.values(),
                    key=lambda m: (-m.capability_tier, m.cost_per_1k_tokens),
                )
        elif task_type == "code":
            # 代码分析 → 中等平衡
            candidates = sorted(
                available.values(),
                key=lambda m: (abs(m.capability_tier - 2), m.cost_per_1k_tokens),
            )
        else:
            candidates = sorted(available.values(), key=lambda m: m.cost_per_1k_tokens)

        return candidates[0] if candidates else list(available.values())[0]

    def report_error(self, model_name: str):
        """报告模型调用失败 (熔断机制)"""
        if model_name in self.registry:
            self.registry[model_name].error_count += 1
            if self.registry[model_name].error_count >= 3:
                self.registry[model_name].is_available = False
                self.registry[model_name].last_check = time.time()
                print(f"⚡ 模型 {model_name} 已熔断 (连续失败 3 次)")

    def report_success(self, model_name: str):
        """报告模型调用成功 (重置错误计数)"""
        if model_name in self.registry:
            self.registry[model_name].error_count = 0
            self.registry[model_name].is_available = True

    def reset_circuit_breakers(self):
        """定时重置熔断器 (建议每 5 分钟调用一次)"""
        now = time.time()
        for model in self.registry.values():
            if not model.is_available and now - model.last_check > 300:
                model.is_available = True
                model.error_count = 0
                print(f"🔄 模型 {model.name} 熔断器已重置")

    def get_status(self) -> list[dict]:
        """获取所有模型状态"""
        return [
            {
                "name": m.name,
                "available": m.is_available,
                "error_count": m.error_count,
                "cost_per_1k": m.cost_per_1k_tokens,
                "max_context": m.max_context,
                "speed_tier": m.speed_tier,
                "capability_tier": m.capability_tier,
            }
            for m in self.registry.values()
        ]

