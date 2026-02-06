"""
管理后台 API — 用户管理、系统统计、Token 用量 (Phase 3)
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_admin, UserOut
from backend.database import get_db
from backend.models.user import User, UserRole
from backend.models.task import AnalysisTask, TaskStatus
from backend.models.token_usage import TokenUsage

router = APIRouter(prefix="/admin", tags=["管理后台"])


class SystemStats(BaseModel):
    total_users: int
    active_users_today: int
    total_tasks: int
    tasks_today: int
    tasks_completed: int
    tasks_failed: int
    total_tokens_today: int
    estimated_cost_today: float


class UserAdminOut(BaseModel):
    id: int
    username: str
    email: str
    display_name: str
    department: str
    role: str
    is_active: bool
    daily_token_limit: int
    storage_limit_mb: int
    total_tasks: int
    tokens_today: int

    model_config = {"from_attributes": True}


class TokenUsageReport(BaseModel):
    date: str
    model_name: str
    total_tokens: int
    request_count: int
    estimated_cost_usd: float


@router.get("/stats", response_model=SystemStats, summary="系统总览统计")
async def get_system_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()

    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0

    # 今日活跃用户 (有登录或有提交任务)
    active_q = select(func.count(func.distinct(AnalysisTask.user_id))).where(
        func.date(AnalysisTask.created_at) == today
    )
    active_users = (await db.execute(active_q)).scalar() or 0

    total_tasks = (await db.execute(select(func.count(AnalysisTask.id)))).scalar() or 0
    tasks_today = (await db.execute(
        select(func.count(AnalysisTask.id)).where(func.date(AnalysisTask.created_at) == today)
    )).scalar() or 0
    tasks_completed = (await db.execute(
        select(func.count(AnalysisTask.id)).where(AnalysisTask.status == TaskStatus.COMPLETED)
    )).scalar() or 0
    tasks_failed = (await db.execute(
        select(func.count(AnalysisTask.id)).where(AnalysisTask.status == TaskStatus.FAILED)
    )).scalar() or 0

    # Token 消耗
    token_q = select(
        func.coalesce(func.sum(TokenUsage.total_tokens), 0),
        func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0),
    ).where(TokenUsage.date == today)
    token_result = (await db.execute(token_q)).one()

    return SystemStats(
        total_users=total_users,
        active_users_today=active_users,
        total_tasks=total_tasks,
        tasks_today=tasks_today,
        tasks_completed=tasks_completed,
        tasks_failed=tasks_failed,
        total_tokens_today=token_result[0],
        estimated_cost_today=round(token_result[1], 4),
    )


@router.get("/users", summary="用户列表")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).order_by(User.created_at.desc())
    total = (await db.execute(select(func.count(User.id)))).scalar() or 0

    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    users = result.scalars().all()

    items = []
    for u in users:
        # 查询该用户任务数和今日 Token
        task_count = (await db.execute(
            select(func.count(AnalysisTask.id)).where(AnalysisTask.user_id == u.id)
        )).scalar() or 0
        tokens_today = (await db.execute(
            select(func.coalesce(func.sum(TokenUsage.total_tokens), 0)).where(
                TokenUsage.user_id == u.id, TokenUsage.date == date.today()
            )
        )).scalar() or 0

        items.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "display_name": u.display_name,
            "department": u.department,
            "role": u.role.value,
            "is_active": u.is_active,
            "daily_token_limit": u.daily_token_limit,
            "storage_limit_mb": u.storage_limit_mb,
            "total_tasks": task_count,
            "tokens_today": tokens_today,
        })

    return {"total": total, "page": page, "items": items}


@router.put("/users/{user_id}/role", summary="修改用户角色")
async def update_user_role(
    user_id: int,
    role: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    user.role = UserRole(role)
    await db.commit()
    return {"message": f"已将 {user.username} 角色更新为 {role}"}


@router.put("/users/{user_id}/quota", summary="修改用户配额")
async def update_user_quota(
    user_id: int,
    daily_token_limit: int | None = None,
    storage_limit_mb: int | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    if daily_token_limit is not None:
        user.daily_token_limit = daily_token_limit
    if storage_limit_mb is not None:
        user.storage_limit_mb = storage_limit_mb
    await db.commit()
    return {"message": "配额已更新"}


@router.get("/token_usage", summary="Token 用量报告 (Phase 3)")
async def get_token_usage_report(
    days: int = Query(7, ge=1, le=90),
    user_id: int | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    start_date = date.today() - timedelta(days=days)
    query = select(TokenUsage).where(TokenUsage.date >= start_date)
    if user_id:
        query = query.where(TokenUsage.user_id == user_id)
    query = query.order_by(TokenUsage.date.desc())

    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "period_days": days,
        "records": [
            {
                "date": str(r.date),
                "user_id": r.user_id,
                "model_name": r.model_name,
                "total_tokens": r.total_tokens,
                "request_count": r.request_count,
                "estimated_cost_usd": round(r.estimated_cost_usd, 4),
            }
            for r in items
        ],
    }

