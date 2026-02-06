"""
Token 计费服务 — 统计每次 LLM 调用的 Token 消耗 (Phase 3)
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.token_usage import TokenUsage
from backend.models.user import User

# DeepSeek 定价 (2024 Q4)
MODEL_PRICING = {
    "deepseek-chat": {"prompt": 0.14 / 1_000_000, "completion": 0.28 / 1_000_000},
    "deepseek-coder": {"prompt": 0.14 / 1_000_000, "completion": 0.28 / 1_000_000},
    "gpt-4o-mini": {"prompt": 0.15 / 1_000_000, "completion": 0.60 / 1_000_000},
    "gpt-4o": {"prompt": 2.50 / 1_000_000, "completion": 10.0 / 1_000_000},
    "qwen-plus": {"prompt": 0.80 / 1_000_000, "completion": 2.0 / 1_000_000},
    "default": {"prompt": 0.50 / 1_000_000, "completion": 1.0 / 1_000_000},
}


def estimate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """估算单次调用成本 (USD)"""
    pricing = MODEL_PRICING.get(model_name, MODEL_PRICING["default"])
    return prompt_tokens * pricing["prompt"] + completion_tokens * pricing["completion"]


async def record_usage(
    db: AsyncSession,
    user_id: int,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
):
    """记录一次 Token 消耗"""
    total = prompt_tokens + completion_tokens
    cost = estimate_cost(model_name, prompt_tokens, completion_tokens)

    today = date.today()

    # 查找今天该模型的记录
    result = await db.execute(
        select(TokenUsage).where(
            TokenUsage.user_id == user_id,
            TokenUsage.date == today,
            TokenUsage.model_name == model_name,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.prompt_tokens += prompt_tokens
        existing.completion_tokens += completion_tokens
        existing.total_tokens += total
        existing.estimated_cost_usd += cost
        existing.request_count += 1
    else:
        record = TokenUsage(
            user_id=user_id,
            date=today,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            estimated_cost_usd=cost,
            request_count=1,
        )
        db.add(record)

    await db.commit()


async def check_daily_limit(db: AsyncSession, user: User) -> tuple:
    """
    检查用户是否超过每日 Token 限额
    Returns: (allowed: bool, used: int, limit: int)
    """
    today = date.today()
    result = await db.execute(
        select(TokenUsage).where(
            TokenUsage.user_id == user.id,
            TokenUsage.date == today,
        )
    )
    records = result.scalars().all()
    used = sum(r.total_tokens for r in records)
    return used < user.daily_token_limit, used, user.daily_token_limit


async def get_user_usage_summary(db: AsyncSession, user_id: int, days: int = 7) -> dict:
    """获取用户近 N 天的使用汇总"""
    from datetime import timedelta
    start = date.today() - timedelta(days=days)

    result = await db.execute(
        select(TokenUsage).where(
            TokenUsage.user_id == user_id,
            TokenUsage.date >= start,
        ).order_by(TokenUsage.date.desc())
    )
    records = result.scalars().all()

    total_tokens = sum(r.total_tokens for r in records)
    total_cost = sum(r.estimated_cost_usd for r in records)
    total_requests = sum(r.request_count for r in records)

    # 按天聚合
    daily = {}
    for r in records:
        d = str(r.date)
        if d not in daily:
            daily[d] = {"tokens": 0, "cost": 0, "requests": 0}
        daily[d]["tokens"] += r.total_tokens
        daily[d]["cost"] += r.estimated_cost_usd
        daily[d]["requests"] += r.request_count

    return {
        "period_days": days,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 4),
        "total_requests": total_requests,
        "daily_breakdown": daily,
    }

