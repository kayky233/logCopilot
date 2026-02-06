"""
Celery 异步分析 Worker — 执行完整的 Multi-Agent Pipeline
"""
import json
import os
import traceback
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.workers.celery_app import celery_app
from backend.config import get_settings

settings = get_settings()


def _get_sync_session():
    """获取同步数据库连接 (Celery worker 不能用 async)"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # 将 async URL 转换为 sync
    db_url = settings.DATABASE_URL.replace("+aiosqlite", "").replace("sqlite://", "sqlite:///")
    if "sqlite" in db_url:
        db_url = settings.DATABASE_URL.replace("+aiosqlite", "")

    engine = create_engine(db_url, echo=settings.DEBUG)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@celery_app.task(bind=True, name="backend.workers.analysis_worker.run_analysis_pipeline")
def run_analysis_pipeline(self, task_uid: str):
    """
    核心异步任务: 执行完整 Multi-Agent 分析流水线

    1. 从 DB 加载任务参数
    2. 读取文件 (日志 + 手册)
    3. 调用 Pipeline
    4. 存储结果到 DB
    5. 更新 Token 使用记录
    """
    from backend.models.task import AnalysisTask, TaskStatus
    from backend.models.analysis import AnalysisResult
    from backend.models.token_usage import TokenUsage
    from backend.models.user import User

    db = _get_sync_session()

    try:
        # 1. 加载任务
        task = db.execute(
            select(AnalysisTask).where(AnalysisTask.task_uid == task_uid)
        ).scalar_one_or_none()

        if not task:
            return {"error": f"Task not found: {task_uid}"}

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)
        db.commit()

        # 2. 加载用户信息获取 API Key
        user = db.execute(select(User).where(User.id == task.user_id)).scalar_one()

        # 3. 读取文件
        user_dir = os.path.join(settings.UPLOAD_DIR, str(user.id))
        log_path = os.path.join(user_dir, "logs", task.log_filename)
        manual_path = os.path.join(user_dir, "manuals", task.manual_domain, task.manual_filename)

        import utils  # 复用已有的文件读取器
        log_content = utils.load_file_content(log_path) if os.path.exists(log_path) else ""
        manual_content = utils.load_file_content(manual_path) if os.path.exists(manual_path) else ""

        if not log_content or not manual_content:
            task.status = TaskStatus.FAILED
            task.error_message = "日志或手册文件为空/不存在"
            task.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {"error": "Missing files"}

        # 4. 日志预处理 (可选初筛)
        final_log = log_content
        filter_keywords = []
        if task.enable_filter and task.filter_keywords:
            try:
                filter_keywords = json.loads(task.filter_keywords)
            except Exception:
                filter_keywords = []

            if filter_keywords:
                filtered = utils.filter_log_content(final_log, filter_keywords)
                if "[System Filter]" not in filtered and len(filtered) > 100:
                    final_log = filtered

        final_log = utils.get_smart_snippet(final_log, head=5000, tail=5000)

        # 5. 执行 Pipeline
        from client import FaultDetectorClient

        # 解密 API Key (Phase 2 简化版，直接取)
        api_key = user.api_key_encrypted  # TODO: 加密解密
        if not api_key:
            task.status = TaskStatus.FAILED
            task.error_message = "用户未配置 API Key"
            task.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {"error": "No API key"}

        detector = FaultDetectorClient(api_key, user.base_url, task.model_name)
        sys_prompt = utils.load_prompt("SYSTEM", task.manual_domain)
        task_prompt = utils.load_prompt("TASK", "default")

        # 调用核心分析
        result, trace_data = detector.analyze(
            manual_content=manual_content,
            log_content=final_log,
            sys_prompt=sys_prompt,
            user_tpl=task_prompt,
            codebase_root="",  # Celery worker 暂不支持代码审计
            enable_code_agent=False,
            focus_keywords=filter_keywords,
        )

        # 6. 存储结果
        analysis = AnalysisResult(
            task_id=task.id,
            is_fault=result.get("is_fault", False),
            confidence=result.get("confidence", 0),
            title=result.get("title", ""),
            reason=result.get("reason", ""),
            fix=result.get("fix", ""),
            manual_guide=trace_data.get("manual_guide", ""),
            log_summary=trace_data.get("log_summary", ""),
            code_insight=trace_data.get("code_insight", ""),
            raw_response=trace_data.get("raw_response", ""),
            pipeline_steps=json.dumps(trace_data.get("steps", []), ensure_ascii=False),
        )
        db.add(analysis)

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        db.commit()

        # 7. 更新 Token 使用记录 (简化估算)
        try:
            total_chars = sum(
                len(str(v)) for v in trace_data.values() if isinstance(v, str)
            )
            est_tokens = int(total_chars * 0.5)  # 粗略估算

            token_record = TokenUsage(
                user_id=user.id,
                date=date.today(),
                model_name=task.model_name,
                total_tokens=est_tokens,
                estimated_cost_usd=est_tokens * 0.000002,  # $2/M tokens 估算
                request_count=4,  # 4 个 Agent 调用
            )
            db.add(token_record)
            analysis.total_tokens_used = est_tokens
            analysis.estimated_cost_usd = est_tokens * 0.000002
            db.commit()
        except Exception:
            pass

        return {"status": "completed", "task_uid": task_uid, "is_fault": result["is_fault"]}

    except Exception as e:
        traceback.print_exc()
        try:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)[:500]
            task.completed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:
            pass
        return {"error": str(e)}
    finally:
        db.close()

