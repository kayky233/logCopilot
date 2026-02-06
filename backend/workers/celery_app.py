"""
Celery 应用配置
"""
from celery import Celery

from backend.config import get_settings

settings = get_settings()

celery_app = Celery(
    "logpilot",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    # 任务超时 (5 分钟)
    task_soft_time_limit=300,
    task_time_limit=360,
    # 并发控制
    worker_concurrency=4,
    worker_prefetch_multiplier=1,
    # 结果保留 24 小时
    result_expires=86400,
    # 任务路由
    task_routes={
        "backend.workers.analysis_worker.*": {"queue": "analysis"},
    },
)

