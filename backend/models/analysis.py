"""
分析结果模型 — 存储 Pipeline 最终输出
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("analysis_tasks.id"), unique=True, nullable=False)

    # 判决结果
    is_fault: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(256), default="未命名故障")
    reason: Mapped[str] = mapped_column(Text, default="")
    fix: Mapped[str] = mapped_column(Text, default="")

    # Agent 中间产物 (调试/审计用)
    manual_guide: Mapped[str] = mapped_column(Text, default="")
    log_summary: Mapped[str] = mapped_column(Text, default="")
    code_insight: Mapped[str] = mapped_column(Text, default="")
    raw_response: Mapped[str] = mapped_column(Text, default="")
    pipeline_steps: Mapped[str] = mapped_column(Text, default="")  # JSON list

    # Token 消耗
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # 时间
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关联
    task = relationship("AnalysisTask", back_populates="result")

