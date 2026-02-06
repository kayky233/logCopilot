"""
后端全局配置 — 环境变量优先，支持 .env 文件
"""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置 (环境变量 > .env > 默认值)"""

    # ---- 应用 ----
    APP_NAME: str = "LogPilot"
    APP_VERSION: str = "3.2.0"
    DEBUG: bool = False

    # ---- 数据库 ----
    DATABASE_URL: str = "sqlite+aiosqlite:///./logpilot.db"

    # ---- Redis (Celery broker + 缓存) ----
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ---- JWT 认证 ----
    SECRET_KEY: str = "logpilot-secret-change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 小时

    # ---- LLM 默认配置 ----
    DEFAULT_LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    DEFAULT_LLM_MODEL: str = "deepseek-chat"

    # ---- 文件存储 ----
    UPLOAD_DIR: str = "storage/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50
    MAX_FILES_PER_USER: int = 100

    # ---- Token 计费 ----
    ENABLE_TOKEN_BILLING: bool = True
    MAX_TOKENS_PER_USER_DAY: int = 500000  # 每用户每天最多消耗 50 万 Token

    # ---- Phase 3: RAG ----
    VECTOR_DB_PATH: str = "storage/vector_db"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()

