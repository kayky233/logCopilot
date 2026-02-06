"""
报告导出 API — Phase 3
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.analysis import AnalysisResult
from backend.models.task import AnalysisTask, TaskStatus
from backend.models.user import User
from backend.services.report_service import export_csv, export_html, export_json

router = APIRouter(prefix="/reports", tags=["报告导出"])


async def _get_user_results(user: User, db: AsyncSession, limit: int = 100) -> list[dict]:
    """获取用户已完成的分析结果"""
    result = await db.execute(
        select(AnalysisTask, AnalysisResult)
        .join(AnalysisResult, AnalysisResult.task_id == AnalysisTask.id)
        .where(
            AnalysisTask.user_id == user.id,
            AnalysisTask.status == TaskStatus.COMPLETED,
        )
        .order_by(AnalysisTask.completed_at.desc())
        .limit(limit)
    )
    rows = result.all()

    items = []
    for task, analysis in rows:
        items.append({
            "log_filename": task.log_filename,
            "manual_filename": task.manual_filename,
            "domain": task.manual_domain,
            "model_name": task.model_name,
            "is_fault": analysis.is_fault,
            "confidence": analysis.confidence,
            "title": analysis.title,
            "reason": analysis.reason,
            "fix": analysis.fix,
            "completed_at": str(task.completed_at) if task.completed_at else "",
        })
    return items


@router.get("/export/json", summary="导出 JSON 报告")
async def export_report_json(
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await _get_user_results(current_user, db, limit)
    return Response(
        content=export_json(items),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=logpilot_report.json"},
    )


@router.get("/export/csv", summary="导出 CSV 报告")
async def export_report_csv(
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await _get_user_results(current_user, db, limit)
    return Response(
        content=export_csv(items),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=logpilot_report.csv"},
    )


@router.get("/export/html", response_class=HTMLResponse, summary="导出 HTML 可视化报告")
async def export_report_html(
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await _get_user_results(current_user, db, limit)
    html = export_html(items, title=f"{current_user.display_name} 的分析报告")
    return HTMLResponse(content=html)

