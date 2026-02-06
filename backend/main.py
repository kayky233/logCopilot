"""
FastAPI 主入口 — LogPilot Backend (Phase 2/3)

启动命令:
  uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.database import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/关闭钩子"""
    # 启动: 创建数据库表 + 必要目录
    await init_db()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.VECTOR_DB_PATH, exist_ok=True)
    print(f"🚀 LogPilot Backend v{settings.APP_VERSION} started")
    yield
    # 关闭
    print("👋 LogPilot Backend shutting down")


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version=settings.APP_VERSION,
    description="基站故障深度判决系统 — RESTful API",
    lifespan=lifespan,
)

# CORS (允许 Streamlit 前端跨域访问)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- 注册路由 ----
from backend.api.auth_routes import router as auth_router
from backend.api.task_routes import router as task_router
from backend.api.file_routes import router as file_router
from backend.api.admin_routes import router as admin_router
from backend.api.report_routes import router as report_router

app.include_router(auth_router, prefix="/api/v1")
app.include_router(task_router, prefix="/api/v1")
app.include_router(file_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(report_router, prefix="/api/v1")


# ---- 健康检查 ----
@app.get("/", tags=["系统"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health", tags=["系统"])
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}

