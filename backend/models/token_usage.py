"""
Token 消耗统计模型 — Phase 3 计费基础
"""
from datetime import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class TokenUsage(Base):
    __tablename__ = "token_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(Date, nullable=False, index=True)

    # 分模型统计
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # 成本估算
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # 请求次数
    request_count: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关联
    user = relationship("User", back_populates="token_usages")

