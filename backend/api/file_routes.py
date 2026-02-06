"""
文件管理 API — 上传/下载/删除 日志和手册
"""
import os
import shutil

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.config import get_settings
from backend.models.user import User

router = APIRouter(prefix="/files", tags=["文件管理"])
settings = get_settings()


def _get_user_dir(user_id: int) -> dict:
    """获取用户文件目录"""
    base = os.path.join(settings.UPLOAD_DIR, str(user_id))
    dirs = {
        "root": base,
        "logs": os.path.join(base, "logs"),
        "manuals": os.path.join(base, "manuals"),
    }
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    return dirs


def _get_storage_usage(user_dir: str) -> dict:
    total = 0
    count = 0
    for dp, _, fns in os.walk(user_dir):
        for f in fns:
            total += os.path.getsize(os.path.join(dp, f))
            count += 1
    return {"total_mb": round(total / 1048576, 2), "file_count": count}


class FileInfo(BaseModel):
    filename: str
    size_kb: float
    category: str  # "log" or "manual"
    domain: str | None = None


class StorageInfo(BaseModel):
    total_mb: float
    file_count: int
    limit_mb: int
    limit_files: int


@router.post("/upload/log", summary="上传日志文件")
async def upload_log(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    dirs = _get_user_dir(current_user.id)

    # 大小检查
    content = await file.read()
    size_mb = len(content) / 1048576
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(400, f"文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")

    usage = _get_storage_usage(dirs["root"])
    if usage["file_count"] >= settings.MAX_FILES_PER_USER:
        raise HTTPException(400, f"文件数已达上限 ({settings.MAX_FILES_PER_USER})")

    filepath = os.path.join(dirs["logs"], file.filename)
    with open(filepath, "wb") as f:
        f.write(content)

    return {"filename": file.filename, "size_mb": round(size_mb, 2), "message": "上传成功"}


@router.post("/upload/manual", summary="上传手册文件")
async def upload_manual(
    file: UploadFile = File(...),
    domain: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    if domain not in ["BSP", "CLK", "SWITCH", "OTHER"]:
        raise HTTPException(400, f"无效的领域: {domain}")

    dirs = _get_user_dir(current_user.id)
    manual_dir = os.path.join(dirs["manuals"], domain)
    os.makedirs(manual_dir, exist_ok=True)

    content = await file.read()
    size_mb = len(content) / 1048576
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(400, f"文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")

    filepath = os.path.join(manual_dir, file.filename)
    with open(filepath, "wb") as f:
        f.write(content)

    return {"filename": file.filename, "domain": domain, "size_mb": round(size_mb, 2)}


@router.get("/list", summary="列出我的所有文件")
async def list_files(current_user: User = Depends(get_current_user)):
    dirs = _get_user_dir(current_user.id)
    files = []

    # 日志
    log_dir = dirs["logs"]
    if os.path.exists(log_dir):
        for f in os.listdir(log_dir):
            fp = os.path.join(log_dir, f)
            files.append(FileInfo(
                filename=f,
                size_kb=round(os.path.getsize(fp) / 1024, 1),
                category="log",
            ))

    # 手册
    for domain in ["BSP", "CLK", "SWITCH", "OTHER"]:
        d = os.path.join(dirs["manuals"], domain)
        if os.path.exists(d):
            for f in os.listdir(d):
                fp = os.path.join(d, f)
                files.append(FileInfo(
                    filename=f,
                    size_kb=round(os.path.getsize(fp) / 1024, 1),
                    category="manual",
                    domain=domain,
                ))

    return {"files": files}


@router.get("/storage", response_model=StorageInfo, summary="查询存储使用情况")
async def get_storage(current_user: User = Depends(get_current_user)):
    dirs = _get_user_dir(current_user.id)
    usage = _get_storage_usage(dirs["root"])
    return StorageInfo(
        total_mb=usage["total_mb"],
        file_count=usage["file_count"],
        limit_mb=current_user.storage_limit_mb,
        limit_files=settings.MAX_FILES_PER_USER,
    )


@router.delete("/{category}/{filename}", summary="删除文件")
async def delete_file(
    category: str,
    filename: str,
    domain: str | None = None,
    current_user: User = Depends(get_current_user),
):
    dirs = _get_user_dir(current_user.id)
    if category == "log":
        filepath = os.path.join(dirs["logs"], filename)
    elif category == "manual" and domain:
        filepath = os.path.join(dirs["manuals"], domain, filename)
    else:
        raise HTTPException(400, "无效的参数")

    # 安全检查
    real = os.path.abspath(filepath)
    base = os.path.abspath(dirs["root"])
    if not real.startswith(base):
        raise HTTPException(403, "安全检查失败")

    if not os.path.exists(filepath):
        raise HTTPException(404, "文件不存在")

    os.remove(filepath)
    return {"deleted": filename}

