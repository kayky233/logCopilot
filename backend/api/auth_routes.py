"""
认证相关 API 路由
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
    authenticate_user,
    create_access_token,
    get_current_user,
    register_user,
)
from backend.config import get_settings
from backend.database import get_db
from backend.models.user import User

router = APIRouter(prefix="/auth", tags=["认证"])
settings = get_settings()


@router.post("/register", response_model=UserOut, summary="用户注册")
async def api_register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user = await register_user(req, db)
    return user


@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def api_login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(req.username, req.password, db)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role.value,
            "department": user.department,
        },
    )


@router.get("/me", response_model=UserOut, summary="获取当前用户信息")
async def api_me(current_user: User = Depends(get_current_user)):
    return current_user

