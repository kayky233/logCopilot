"""
用户模型 — 支持 JWT 认证、角色、部门归属
"""
import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), default="")
    department: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)

    # LLM 配置 (每用户独立)
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    base_url: Mapped[str] = mapped_column(String(256), default="https://api.deepseek.com/v1")
    model_name: Mapped[str] = mapped_column(String(64), default="deepseek-chat")

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 配额
    daily_token_limit: Mapped[int] = mapped_column(Integer, default=500000)
    storage_limit_mb: Mapped[int] = mapped_column(Integer, default=500)

    # 关联
    tasks = relationship("AnalysisTask", back_populates="user", lazy="dynamic")
    token_usages = relationship("TokenUsage", back_populates="user", lazy="dynamic")

