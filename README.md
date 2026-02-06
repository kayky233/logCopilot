# 📡 LogPilot — 基站故障深度判决系统

> Multi-Agent AI 驱动的基站日志自动化故障诊断平台

LogPilot 是一款面向通信基站运维团队的智能故障判决工具。它通过 **四个 AI Agent 协作流水线**，将故障手册知识与实际日志进行深度比对，自动输出结构化的故障诊断报告。

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🤖 **Multi-Agent Pipeline** | Manual → Log → Code → Boss 四阶段协作判决 |
| 📚 **手册驱动** | 先研读故障手册提取判据规则，再到日志中精确搜证 |
| 💻 **代码审计** | 可选挂载本地代码库，AI 自动读取报错位置的源码分析根因 |
| 🔍 **日志智能初筛** | 基于关键词 + 上下文行的日志降噪，大幅减少 Token 消耗 |
| 👥 **多用户隔离** | 独立工作空间、独立配置、独立存储配额 |
| ⚡ **LLM 缓存** | 手册特征词 24h 缓存，避免重复调用 |
| 🏢 **生产级后端** | FastAPI + Celery + JWT 认证，支持 100+ 并发用户 |
| 📊 **批量分析 & 报告** | 批量提交任务，导出 JSON / CSV / HTML 报告 |
| 🧠 **多模型路由** | 按任务类型自动选择最优模型，内置熔断保护 |
| 📖 **RAG 知识库** | 手册向量化语义检索，千级手册秒级召回 |
| 💰 **Token 计费** | 分模型计费统计，用户每日配额控制 |

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────┐
│                    Streamlit 前端                      │
│  用户上传手册/日志 → 选择场景 → 查看诊断报告            │
└────────────────────────┬─────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────┐
│              FastAPI 后端 (Phase 2)                    │
│  JWT 认证 │ 任务管理 │ 文件管理 │ 管理后台 │ 报告导出  │
└────────────────────────┬─────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────┐
│           Multi-Agent Pipeline (核心)                  │
│                                                       │
│  📚 Manual Agent ──→ 🕵️ Log Agent ──→ 💻 Code Agent  │
│         │                                    │        │
│         └──────────→ 🧠 Boss Agent ←─────────┘        │
│                         │                             │
│                    最终判决报告                         │
└───────────────────────────────────────────────────────┘
```

---

## 📂 项目结构

```
logCopilot/
├── app.py                          # Streamlit 主入口
├── ui.py                           # UI 组件
├── utils.py                        # 工具库 (用户隔离/缓存/文件IO)
├── client.py                       # Pipeline 客户端
├── agents.py                       # 四个 AI Agent 定义
├── code_utils.py                   # 代码片段安全读取
│
├── backend/                        # FastAPI 后端
│   ├── main.py                     # 后端入口
│   ├── config.py                   # 环境变量配置
│   ├── auth.py                     # JWT 认证
│   ├── database.py                 # 异步数据库
│   ├── api/                        # API 路由
│   │   ├── auth_routes.py          #   认证 (注册/登录)
│   │   ├── task_routes.py          #   任务 (提交/查询/批量)
│   │   ├── file_routes.py          #   文件 (上传/下载/删除)
│   │   ├── admin_routes.py         #   管理后台
│   │   └── report_routes.py        #   报告导出
│   ├── models/                     # 数据库模型
│   │   ├── user.py                 #   用户 (角色/配额)
│   │   ├── task.py                 #   分析任务
│   │   ├── analysis.py             #   分析结果
│   │   └── token_usage.py          #   Token 消耗记录
│   ├── services/                   # 业务服务
│   │   ├── model_router.py         #   多模型智能路由
│   │   ├── rag_service.py          #   RAG 向量检索
│   │   ├── report_service.py       #   报告生成
│   │   └── token_service.py        #   计费服务
│   └── workers/                    # 异步任务
│       ├── celery_app.py           #   Celery 配置
│       └── analysis_worker.py      #   分析 Worker
│
├── docker/                         # 容器化部署
│   ├── Dockerfile
│   ├── docker-compose.yml          # 一键编排 (5 个服务)
│   └── nginx.conf                  # 反向代理
│
├── tests/                          # 测试 (30 项)
│   ├── test_phase1.py              # 用户隔离/缓存/安全
│   ├── test_phase2_api.py          # API 接口
│   └── test_phase3.py              # 模型路由/报告/RAG
│
├── prompts/                        # Prompt 模板 (可热编辑)
├── requirements.txt                # 前端依赖
├── requirements-backend.txt        # 后端完整依赖
└── .env.example                    # 环境变量模板
```

---

## 🚀 快速开始

### 方式一：Streamlit 单机模式 (开发/演示)

```bash
# 1. 克隆项目
git clone https://github.com/kayky233/logCopilot.git
cd logCopilot

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动
streamlit run app.py
```

打开浏览器 → 左侧边栏填入 **API Key** → 上传手册和日志 → 点击扫描。

### 方式二：Docker 全栈部署 (生产)

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 SECRET_KEY 等

# 2. 一键启动
docker-compose -f docker/docker-compose.yml up -d

# 服务地址:
#   前端:  http://localhost (Nginx)
#   API:   http://localhost/api/v1
#   Docs:  http://localhost:8000/docs (Swagger)
```

### 方式三：手动启动后端 (开发调试)

```bash
pip install -r requirements-backend.txt

# 启动 Redis
redis-server

# 启动 FastAPI
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 启动 Celery Worker
celery -A backend.workers.celery_app worker -l info -Q analysis -c 4

# 启动前端
streamlit run app.py
```

---

## 🔧 配置说明

### LLM 配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| Base URL | `https://api.deepseek.com/v1` | 兼容 OpenAI 格式的 API 地址 |
| Model | `deepseek-chat` | 模型名称 |
| API Key | — | 在侧边栏或 `.env` 中配置 |

支持所有 OpenAI 兼容接口：DeepSeek、通义千问、GPT-4o、本地 Ollama 等。

### 手册格式

支持 `.md` / `.txt` / `.pdf` / `.docx` 格式。推荐 Markdown，示例：

```markdown
# 故障定义：系统主时钟 PLL 失锁

## 日志特征 (判据)
1. `PLL status changed: LOCK -> UNLOCK`
2. `Fatal Error: System PLL lost lock, current_state=0x3`

## 排查步骤
1. 检查 GPS 天线连接
2. 检查参考源配置
```

---

## 🧪 运行测试

```bash
# 全部测试 (30 项)
python -m pytest tests/ -v

# 按阶段测试
python -m pytest tests/test_phase1.py -v   # 用户隔离/缓存
python -m pytest tests/test_phase3.py -v   # 模型路由/报告/RAG
```

---

## 📋 API 接口概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 用户注册 |
| POST | `/api/v1/auth/login` | 登录获取 JWT |
| GET | `/api/v1/auth/me` | 当前用户信息 |
| POST | `/api/v1/tasks/submit` | 提交分析任务 |
| POST | `/api/v1/tasks/submit_batch` | 批量提交 |
| GET | `/api/v1/tasks/status/{uid}` | 查询任务状态 |
| GET | `/api/v1/tasks/result/{uid}` | 获取分析结果 |
| GET | `/api/v1/tasks/list` | 我的任务列表 |
| POST | `/api/v1/files/upload/log` | 上传日志 |
| POST | `/api/v1/files/upload/manual` | 上传手册 |
| GET | `/api/v1/files/storage` | 存储用量 |
| GET | `/api/v1/reports/export/html` | 导出 HTML 报告 |
| GET | `/api/v1/reports/export/csv` | 导出 CSV 报告 |
| GET | `/api/v1/admin/stats` | 系统统计 (管理员) |
| GET | `/api/v1/admin/token_usage` | Token 用量报告 |

完整文档启动后访问：`http://localhost:8000/docs`

---

## 🗺️ 演进路线

| 阶段 | 目标 | 状态 |
|------|------|------|
| **Phase 1** | 单机加固：用户隔离、缓存、文件限制 | ✅ 已完成 |
| **Phase 2** | 生产架构：FastAPI + JWT + Celery + Docker | ✅ 已完成 |
| **Phase 3** | 规模运营：多模型路由、RAG、报告、计费 | ✅ 已完成 |
| Phase 4 | 🔜 前端重构 (Vue/React)、LDAP/SSO 对接 | 规划中 |
| Phase 5 | 🔜 持续学习：用户反馈闭环、自动更新判据 | 规划中 |

---

## 📄 License

MIT License

---

> **LogPilot** — 让每一次基站告警都有据可依 📡

