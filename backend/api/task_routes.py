"""
分析任务 API 路由 — 提交任务、查询进度、获取结果
"""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.task import AnalysisTask, TaskStatus
from backend.models.analysis import AnalysisResult
from backend.models.user import User

router = APIRouter(prefix="/tasks", tags=["分析任务"])


# ---- Schemas ----
class TaskCreateRequest(BaseModel):
    log_filename: str
    manual_domain: str
    manual_filename: str
    model_name: str = "deepseek-chat"
    enable_code_agent: bool = True
    enable_filter: bool = False
    filter_keywords: list[str] = []


class TaskOut(BaseModel):
    id: int
    task_uid: str
    status: str
    log_filename: str
    manual_domain: str
    manual_filename: str
    model_name: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}


class TaskResultOut(BaseModel):
    task_uid: str
    status: str
    is_fault: bool | None = None
    confidence: int | None = None
    title: str | None = None
    reason: str | None = None
    fix: str | None = None
    manual_guide: str | None = None
    log_summary: str | None = None
    code_insight: str | None = None
    pipeline_steps: list[str] | None = None
    total_tokens_used: int | None = None

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[TaskOut]


class BatchTaskRequest(BaseModel):
    """Phase 3: 批量提交"""
    tasks: list[TaskCreateRequest]


# ---- Routes ----

@router.post("/submit", response_model=TaskOut, summary="提交分析任务")
async def submit_task(
    req: TaskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = AnalysisTask(
        task_uid=str(uuid.uuid4()),
        user_id=current_user.id,
        log_filename=req.log_filename,
        manual_domain=req.manual_domain,
        manual_filename=req.manual_filename,
        model_name=req.model_name,
        enable_code_agent=req.enable_code_agent,
        enable_filter=req.enable_filter,
        filter_keywords=json.dumps(req.filter_keywords, ensure_ascii=False),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 触发 Celery 异步任务
    try:
        from backend.workers.analysis_worker import run_analysis_pipeline
        celery_result = run_analysis_pipeline.delay(task.task_uid)
        task.celery_task_id = celery_result.id
        await db.commit()
    except Exception as e:
        # Celery 未启动时降级为同步 (开发模式)
        print(f"⚠️ Celery 未连接，任务将等待手动执行: {e}")

    return task


@router.post("/submit_batch", summary="批量提交分析任务 (Phase 3)")
async def submit_batch(
    req: BatchTaskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task_uids = []
    for item in req.tasks:
        task = AnalysisTask(
            task_uid=str(uuid.uuid4()),
            user_id=current_user.id,
            log_filename=item.log_filename,
            manual_domain=item.manual_domain,
            manual_filename=item.manual_filename,
            model_name=item.model_name,
            enable_code_agent=item.enable_code_agent,
            enable_filter=item.enable_filter,
            filter_keywords=json.dumps(item.filter_keywords, ensure_ascii=False),
        )
        db.add(task)
        task_uids.append(task.task_uid)

    await db.commit()

    # 批量触发 Celery
    for uid in task_uids:
        try:
            from backend.workers.analysis_worker import run_analysis_pipeline
            run_analysis_pipeline.delay(uid)
        except Exception:
            pass

    return {"submitted": len(task_uids), "task_uids": task_uids}


@router.get("/status/{task_uid}", response_model=TaskOut, summary="查询任务状态")
async def get_task_status(
    task_uid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisTask).where(
            AnalysisTask.task_uid == task_uid,
            AnalysisTask.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/result/{task_uid}", response_model=TaskResultOut, summary="获取分析结果")
async def get_task_result(
    task_uid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisTask).where(
            AnalysisTask.task_uid == task_uid,
            AnalysisTask.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status != TaskStatus.COMPLETED:
        return TaskResultOut(task_uid=task_uid, status=task.status.value)

    # 加载结果
    r = await db.execute(select(AnalysisResult).where(AnalysisResult.task_id == task.id))
    analysis = r.scalar_one_or_none()
    if not analysis:
        return TaskResultOut(task_uid=task_uid, status="completed_no_result")

    steps = []
    if analysis.pipeline_steps:
        try:
            steps = json.loads(analysis.pipeline_steps)
        except Exception:
            pass

    return TaskResultOut(
        task_uid=task_uid,
        status=task.status.value,
        is_fault=analysis.is_fault,
        confidence=analysis.confidence,
        title=analysis.title,
        reason=analysis.reason,
        fix=analysis.fix,
        manual_guide=analysis.manual_guide[:500] if analysis.manual_guide else None,
        log_summary=analysis.log_summary[:500] if analysis.log_summary else None,
        code_insight=analysis.code_insight[:500] if analysis.code_insight else None,
        pipeline_steps=steps,
        total_tokens_used=analysis.total_tokens_used,
    )


@router.get("/list", response_model=TaskListResponse, summary="查询我的任务列表")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(AnalysisTask).where(AnalysisTask.user_id == current_user.id)
    if status_filter:
        query = query.where(AnalysisTask.status == status_filter)
    query = query.order_by(AnalysisTask.created_at.desc())

    # 总数
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return TaskListResponse(total=total, page=page, page_size=page_size, items=items)


@router.delete("/{task_uid}", summary="取消/删除任务")
async def cancel_task(
    task_uid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisTask).where(
            AnalysisTask.task_uid == task_uid,
            AnalysisTask.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status == TaskStatus.PENDING:
        task.status = TaskStatus.CANCELLED
        await db.commit()

    return {"status": "cancelled", "task_uid": task_uid}

