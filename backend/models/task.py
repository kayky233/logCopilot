"""
分析任务模型 — 异步任务队列的核心实体
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class TaskStatus(str, enum.Enum):
    PENDING = "pending"          # 等待队列
    RUNNING = "running"          # 正在执行
    COMPLETED = "completed"      # 完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 用户取消


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)  # UUID
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.PENDING)

    # 输入参数
    log_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    manual_domain: Mapped[str] = mapped_column(String(32), nullable=False)
    manual_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), default="deepseek-chat")
    enable_code_agent: Mapped[bool] = mapped_column(default=True)
    enable_filter: Mapped[bool] = mapped_column(default=False)
    filter_keywords: Mapped[str] = mapped_column(Text, default="")  # JSON list

    # Celery 任务 ID
    celery_task_id: Mapped[str] = mapped_column(String(64), nullable=True)

    # 时间追踪
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 错误信息
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # 关联
    user = relationship("User", back_populates="tasks")
    result = relationship("AnalysisResult", back_populates="task", uselist=False)

