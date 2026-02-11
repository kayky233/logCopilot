# ===== LogPilot Docker Image =====
# 多阶段构建: 减小最终镜像体积
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-backend.txt .
RUN pip install --no-cache-dir -r requirements-backend.txt

# ===== 运行时镜像 =====
FROM python:3.11-slim

WORKDIR /app

# 复制 Python 包
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制项目代码
COPY . .

# 创建必要目录
RUN mkdir -p storage/uploads storage/vector_db prompts user_configs

# 暴露端口
EXPOSE 8000
EXPOSE 8501

# 健康检查 (python:3.11-slim 无 curl，使用 python 内置 urllib)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 默认启动 FastAPI 后端
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

