"""
Phase 2 验证测试 — FastAPI 后端 API
运行: python -m pytest tests/test_phase2_api.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.database import init_db, engine, Base


@pytest.fixture(autouse=True)
async def setup_db():
    """每次测试重建数据库"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_check(client):
    """健康检查接口"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root(client):
    """根路径"""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "LogPilot" in resp.json()["name"]


@pytest.mark.asyncio
async def test_register_and_login(client):
    """注册 + 登录流程"""
    # 注册
    resp = await client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "Test1234!",
        "display_name": "测试用户",
        "department": "研发部",
    })
    assert resp.status_code == 200
    user = resp.json()
    assert user["username"] == "testuser"

    # 登录
    resp = await client.post("/api/v1/auth/login", json={
        "username": "testuser",
        "password": "Test1234!",
    })
    assert resp.status_code == 200
    token_data = resp.json()
    assert "access_token" in token_data

    # 获取当前用户
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_duplicate_register(client):
    """重复注册应失败"""
    await client.post("/api/v1/auth/register", json={
        "username": "dup_user",
        "email": "dup@example.com",
        "password": "Test1234!",
    })
    resp = await client.post("/api/v1/auth/register", json={
        "username": "dup_user",
        "email": "dup2@example.com",
        "password": "Test1234!",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_wrong_password(client):
    """错误密码应被拒绝"""
    await client.post("/api/v1/auth/register", json={
        "username": "authuser",
        "email": "auth@example.com",
        "password": "correct_pw",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "username": "authuser",
        "password": "wrong_pw",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unauthorized_access(client):
    """未认证不能访问受保护接口"""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401

    resp = await client.get("/api/v1/tasks/list")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_submit_and_list_tasks(client):
    """提交任务 + 查询任务列表"""
    # 注册 + 登录
    await client.post("/api/v1/auth/register", json={
        "username": "taskuser",
        "email": "task@example.com",
        "password": "Task1234!",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "username": "taskuser",
        "password": "Task1234!",
    })
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 提交任务
    resp = await client.post("/api/v1/tasks/submit", headers=headers, json={
        "log_filename": "test.log",
        "manual_domain": "CLK",
        "manual_filename": "pll_fault.md",
    })
    assert resp.status_code == 200
    task = resp.json()
    assert task["status"] == "pending"
    task_uid = task["task_uid"]

    # 查询状态
    resp = await client.get(f"/api/v1/tasks/status/{task_uid}", headers=headers)
    assert resp.status_code == 200

    # 查询列表
    resp = await client.get("/api/v1/tasks/list", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_file_storage_info(client):
    """查询存储信息"""
    await client.post("/api/v1/auth/register", json={
        "username": "storageuser",
        "email": "storage@example.com",
        "password": "Store1234!",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "username": "storageuser",
        "password": "Store1234!",
    })
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/files/storage", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_mb" in data
    assert "limit_mb" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

