"""
utils.py — LogPilot 核心工具模块 (Phase 1: 用户隔离版)

变更记录:
  - v3.1: 用户工作空间隔离、文件大小限制、LLM 缓存层
"""
import hashlib
import json
import os
import shutil
import time

import pandas as pd
import streamlit as st

# ==========================================
# 0. 依赖库懒加载 (防止未安装库导致闪退)
# ==========================================
try:
    import docx
except ImportError:
    docx = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

# ==========================================
# 1. 全局配置
# ==========================================
BASE_DIR = "analysis_workspace"
PROMPT_DIR = "prompts"
CONFIG_DIR = "user_configs"
CACHE_DIR = os.path.join(BASE_DIR, "cache")

# ---- 安全限制 ----
MAX_UPLOAD_SIZE_MB = 50          # 单文件最大 50MB
MAX_FILES_PER_USER = 100         # 每用户最多 100 个文件
MAX_TOTAL_STORAGE_MB = 500       # 每用户最大 500MB 总存储

# ---- 代码库与路径映射配置 ----
CODEBASE_CONFIG_PATH = os.path.join(CONFIG_DIR, "codebase_path.txt")
PATH_MAP_CONFIG_PATH = os.path.join(CONFIG_DIR, "path_mapping.txt")

# ---- 领域定义 ----
DOMAINS = ["BSP", "CLK", "SWITCH", "OTHER"]


# ==========================================
# 2. 初始资产 (Prompt 默认值)
# ==========================================
INIT_SYSTEM_PROMPTS = {
    "BSP": """# Role
你是一个基站 BSP (Board Support Package) 系统的故障判决专家。

# Context
负责分析启动流程、驱动加载、内存管理及硬件抽象层故障。
约束：
1. 严格依据手册判据，禁止发散。
2. 区分启动阶段的瞬态报错与永久失败。
3. 输出严格的 JSON 格式。""",
    "CLK": """# Role
你是一个基站时钟与同步子系统 (CLK) 的故障判决专家。

# Context
负责 GNSS、1588v2、PLL 状态及时钟源切换分析。
约束：
1. 重点关注 Lock/Unlock 状态切换及时序。
2. 区分隐性故障（相位偏差）与显性故障（告警）。
3. 输出严格的 JSON 格式。""",
    "SWITCH": """# Role
你是一个基站交换与网络子系统 (SWITCH) 的故障判决专家。

# Context
负责 VLAN、端口状态、风暴抑制及报文转发分析。
约束：
1. 区分物理链路抖动与逻辑配置错误。
2. 输出严格的 JSON 格式。""",
    "OTHER": """# Role
你是一个通用的自动化故障判决专家。

请严格根据参考手册判断日志中是否存在故障。输出 JSON 格式。""",
}

INIT_TASK_TEMPLATE = """# Task
请分析以下日志是否满足故障手册中的定义。

## Input Data
【参考手册】:
{manual_content}

【系统日志】:
{log_content}

## Output Format (JSON Only)
{
    "is_fault": true,
    "confidence": 95,
    "title": "故障名称 (From Manual)",
    "reason": "简要证据链...",
    "fix": "修复建议..."
}"""


# ==========================================
# 3. 用户工作空间管理 (Phase 1 核心)
# ==========================================

def _sanitize_user_id(user_id: str) -> str:
    """安全化用户 ID (防目录遍历)"""
    safe = "".join([c for c in str(user_id) if c.isalnum() or c in "_-"]) or "default"
    return safe[:64]  # 限制长度


def get_user_workspace(user_id: str) -> dict:
    """
    获取用户独立工作空间路径。
    每个用户拥有自己的 logs/ 和 manuals/ 目录。
    返回 dict: {root, logs, manuals}
    """
    safe_id = _sanitize_user_id(user_id)
    root = os.path.join(BASE_DIR, "workspaces", safe_id)
    paths = {
        "root": root,
        "logs": os.path.join(root, "logs"),
        "manuals": root,  # manuals 仍按 domain 分，在 root 下
    }
    return paths


def get_user_log_dir(user_id: str) -> str:
    return get_user_workspace(user_id)["logs"]


def get_user_manual_root(user_id: str) -> str:
    return os.path.join(get_user_workspace(user_id)["root"], "manuals")


# ---- 兼容旧版的全局路径 (供 Prompt/Config 使用，不隔离) ----
SHARED_MANUAL_ROOT_DIR = os.path.join(BASE_DIR, "shared_manuals")
LOG_DIR = os.path.join(BASE_DIR, "logs")            # 保留兼容
MANUAL_ROOT_DIR = os.path.join(BASE_DIR, "manuals")  # 保留兼容


def init_environment(user_id: str = "default"):
    """初始化目录并生成默认 Prompt 文件"""
    # 全局目录
    for d in [BASE_DIR, PROMPT_DIR, CONFIG_DIR, CACHE_DIR, SHARED_MANUAL_ROOT_DIR]:
        os.makedirs(d, exist_ok=True)

    # 用户工作空间
    ws = get_user_workspace(user_id)
    os.makedirs(ws["logs"], exist_ok=True)
    manual_root = get_user_manual_root(user_id)
    for domain in DOMAINS:
        os.makedirs(os.path.join(manual_root, domain), exist_ok=True)

    # 共享手册目录 (管理员统一维护的标准手册)
    for domain in DOMAINS:
        os.makedirs(os.path.join(SHARED_MANUAL_ROOT_DIR, domain), exist_ok=True)

    # System Prompts
    for domain in DOMAINS:
        sys_path = os.path.join(PROMPT_DIR, f"system_{domain}.md")
        if not os.path.exists(sys_path):
            with open(sys_path, "w", encoding="utf-8") as f:
                f.write(INIT_SYSTEM_PROMPTS.get(domain, INIT_SYSTEM_PROMPTS["OTHER"]))

    # Task Template
    task_path = os.path.join(PROMPT_DIR, "task_default.md")
    if not os.path.exists(task_path):
        with open(task_path, "w", encoding="utf-8") as f:
            f.write(INIT_TASK_TEMPLATE)


def clear_user_workspace(user_id: str):
    """清空指定用户的工作数据"""
    ws = get_user_workspace(user_id)
    if os.path.exists(ws["root"]):
        shutil.rmtree(ws["root"])
    init_environment(user_id)


def get_user_storage_usage(user_id: str) -> dict:
    """统计用户存储使用情况"""
    ws = get_user_workspace(user_id)
    total_bytes = 0
    file_count = 0
    for dirpath, _, filenames in os.walk(ws["root"]):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_bytes += os.path.getsize(fp)
            file_count += 1
    return {
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "file_count": file_count,
        "limit_mb": MAX_TOTAL_STORAGE_MB,
        "limit_files": MAX_FILES_PER_USER,
    }


# ==========================================
# 4. Prompt 管理接口
# ==========================================
def get_prompt_path(layer, name):
    if layer == "SYSTEM":
        return os.path.join(PROMPT_DIR, f"system_{name}.md")
    if layer == "TASK":
        return os.path.join(PROMPT_DIR, f"task_{name}.md")
    return None


def load_prompt(layer, name):
    """读取 Prompt，优先读文件"""
    path = get_prompt_path(layer, name)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    if layer == "SYSTEM":
        return INIT_SYSTEM_PROMPTS.get(name, INIT_SYSTEM_PROMPTS["OTHER"])
    return INIT_TASK_TEMPLATE


def save_prompt(layer, name, content):
    path = get_prompt_path(layer, name)
    if path:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception:
            pass
    return False


# ==========================================
# 5. 用户配置管理
# ==========================================
def get_config_path(user_id):
    safe_id = _sanitize_user_id(user_id)
    return os.path.join(CONFIG_DIR, f"config_{safe_id}.json")


def load_user_config(user_id):
    path = get_config_path(user_id)
    default = {
        "base_url": "https://api.deepseek.com/v1",
        "model_name": "deepseek-chat",
        "api_key": "",
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return {**default, **json.load(f)}
        except Exception:
            pass
    return default


def save_user_config(user_id, config_data):
    try:
        with open(get_config_path(user_id), "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
        return True
    except Exception:
        return False


# ==========================================
# 6. 本地代码库与路径映射配置
# ==========================================
def load_codebase_root():
    if os.path.exists(CODEBASE_CONFIG_PATH):
        with open(CODEBASE_CONFIG_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def save_codebase_root(path):
    try:
        os.makedirs(os.path.dirname(CODEBASE_CONFIG_PATH), exist_ok=True)
        with open(CODEBASE_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(path.strip())
        return True, "已保存"
    except Exception as e:
        return False, str(e)


def load_path_prefix():
    if os.path.exists(PATH_MAP_CONFIG_PATH):
        with open(PATH_MAP_CONFIG_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def save_path_prefix(prefix):
    try:
        os.makedirs(os.path.dirname(PATH_MAP_CONFIG_PATH), exist_ok=True)
        with open(PATH_MAP_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(prefix.strip())
        return True, "已保存"
    except Exception as e:
        return False, str(e)


# ==========================================
# 7. 文件 IO 与解析 (安全增强版)
# ==========================================

def check_upload_allowed(user_id: str, file_size_bytes: int) -> tuple:
    """
    检查是否允许上传 (Phase 1 安全)
    Returns: (allowed: bool, reason: str)
    """
    # 单文件大小检查
    size_mb = file_size_bytes / (1024 * 1024)
    if size_mb > MAX_UPLOAD_SIZE_MB:
        return False, f"文件超过 {MAX_UPLOAD_SIZE_MB}MB 限制 (当前 {size_mb:.1f}MB)"

    # 用户总存储检查
    usage = get_user_storage_usage(user_id)
    if usage["file_count"] >= MAX_FILES_PER_USER:
        return False, f"文件数已达上限 ({MAX_FILES_PER_USER}个)"
    if usage["total_mb"] + size_mb > MAX_TOTAL_STORAGE_MB:
        return False, f"存储空间不足 (已用 {usage['total_mb']}MB / {MAX_TOTAL_STORAGE_MB}MB)"

    return True, "OK"


def load_file_content(filepath):
    """
    通用文件读取器：支持 .md, .txt, .log, .xlsx, .csv, .docx, .pdf
    """
    try:
        ext = os.path.splitext(filepath)[1].lower()

        if ext in [".xlsx", ".xls"]:
            return pd.read_excel(filepath).astype(str).agg(" ".join, axis=1).str.cat(sep="\n")

        if ext == ".csv":
            try:
                df = pd.read_csv(filepath, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(filepath, encoding="gbk")
            return df.astype(str).agg(" ".join, axis=1).str.cat(sep="\n")

        if ext == ".docx":
            if docx is None:
                return "❌ 错误: 未安装 python-docx 库"
            doc = docx.Document(filepath)
            return "\n".join([para.text for para in doc.paragraphs])

        if ext == ".pdf":
            if PdfReader is None:
                return "❌ 错误: 未安装 pypdf 库"
            reader = PdfReader(filepath)
            return "\n".join([page.extract_text() or "" for page in reader.pages])

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"❌ 文件解析失败 ({os.path.basename(filepath)}): {str(e)}"


def get_manuals_by_domain(user_id: str = "default"):
    """获取用户手册列表 (合并: 用户私有 + 共享)"""
    tree = {}
    user_manual_root = get_user_manual_root(user_id)

    for d in DOMAINS:
        files = set()
        # 用户私有手册
        user_path = os.path.join(user_manual_root, d)
        if os.path.exists(user_path):
            files.update(
                f for f in os.listdir(user_path)
                if f.lower().endswith((".md", ".pdf", ".docx", ".txt"))
            )
        # 共享手册
        shared_path = os.path.join(SHARED_MANUAL_ROOT_DIR, d)
        if os.path.exists(shared_path):
            files.update(
                f for f in os.listdir(shared_path)
                if f.lower().endswith((".md", ".pdf", ".docx", ".txt"))
            )
        tree[d] = sorted(files)

    return tree


def resolve_manual_path(user_id: str, domain: str, filename: str) -> str:
    """解析手册文件的实际路径 (用户私有 > 共享)"""
    user_path = os.path.join(get_user_manual_root(user_id), domain, filename)
    if os.path.exists(user_path):
        return user_path
    shared_path = os.path.join(SHARED_MANUAL_ROOT_DIR, domain, filename)
    if os.path.exists(shared_path):
        return shared_path
    # 兼容旧路径
    old_path = os.path.join(MANUAL_ROOT_DIR, domain, filename)
    if os.path.exists(old_path):
        return old_path
    return user_path  # fallback


def save_uploaded_manuals(uploaded_files, domain, user_id="default"):
    target_dir = os.path.join(get_user_manual_root(user_id), domain)
    os.makedirs(target_dir, exist_ok=True)
    saved = 0
    for f in uploaded_files:
        allowed, reason = check_upload_allowed(user_id, f.size)
        if not allowed:
            st.error(f"❌ {f.name}: {reason}")
            continue
        with open(os.path.join(target_dir, f.name), "wb") as out_f:
            out_f.write(f.getbuffer())
        saved += 1
    if saved > 0:
        st.toast(f"✅ {saved} 个手册已上传至 {domain}", icon="📚")


def save_uploaded_logs(uploaded_files, user_id="default"):
    log_dir = get_user_log_dir(user_id)
    os.makedirs(log_dir, exist_ok=True)
    saved = 0
    for f in uploaded_files:
        allowed, reason = check_upload_allowed(user_id, f.size)
        if not allowed:
            st.error(f"❌ {f.name}: {reason}")
            continue
        with open(os.path.join(log_dir, f.name), "wb") as out_f:
            out_f.write(f.getbuffer())
        saved += 1
    if saved > 0:
        st.toast(f"✅ {saved} 个日志已上传", icon="🪵")


def delete_files(dir_path, filenames):
    for f in filenames:
        try:
            os.remove(os.path.join(dir_path, f))
        except Exception:
            pass
    st.toast(f"🗑️ 已删除 {len(filenames)} 个文件", icon="🧹")


# ==========================================
# 8. LLM 结果缓存 (Phase 1)
# ==========================================

def _make_cache_key(*args) -> str:
    """根据输入内容生成缓存 key"""
    content = "|".join(str(a)[:5000] for a in args)
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def cache_get(namespace: str, *args) -> str | None:
    """读取缓存，返回 None 表示未命中"""
    key = _make_cache_key(*args)
    cache_file = os.path.join(CACHE_DIR, namespace, f"{key}.json")
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 检查过期 (默认 24 小时)
        if time.time() - data.get("ts", 0) > 86400:
            os.remove(cache_file)
            return None
        return data.get("value", "")
    except Exception:
        return None


def cache_set(namespace: str, value: str, *args):
    """写入缓存"""
    key = _make_cache_key(*args)
    cache_dir = os.path.join(CACHE_DIR, namespace)
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{key}.json")
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "value": value}, f, ensure_ascii=False)
    except Exception:
        pass


def cache_clear(namespace: str = ""):
    """清空缓存"""
    target = os.path.join(CACHE_DIR, namespace) if namespace else CACHE_DIR
    if os.path.exists(target):
        shutil.rmtree(target)
        os.makedirs(target, exist_ok=True)


# ==========================================
# 9. 日志处理工具
# ==========================================
def get_smart_snippet(content: str, head: int = 3000, tail: int = 3000) -> str:
    """提取日志头尾的智能摘要 (同时降低 Token 消耗)"""
    if not content:
        return ""
    char_limit = head + tail + 200
    if len(content) <= char_limit:
        return content

    head_part = content[:head]
    tail_part = content[-tail:] if tail > 0 else ""
    return f"{head_part}\n\n... (中间省略 {len(content) - head - tail} 字符) ...\n\n{tail_part}"


def filter_log_content(content: str, keywords: list, context_lines: int = 5) -> str:
    """关键日志初筛算法 (基于索引集去重)"""
    if not content or not keywords:
        return content

    lines = content.splitlines()
    total_lines = len(lines)
    keep_indices = set()

    valid_keywords = [k.lower().strip() for k in keywords if k and k.strip()]
    if not valid_keywords:
        return content

    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(kw in line_lower for kw in valid_keywords):
            start = max(0, i - context_lines)
            end = min(total_lines, i + context_lines + 1)
            keep_indices.update(range(start, end))

    if not keep_indices:
        return (
            f"[System Filter]: 在 {total_lines} 行日志中未找到关键词 "
            f"{valid_keywords}，请检查关键词配置或关闭初筛。"
        )

    sorted_indices = sorted(list(keep_indices))
    result_lines = []
    last_idx = -1
    for idx in sorted_indices:
        if last_idx != -1 and idx > last_idx + 1:
            result_lines.append(f"\n... (过滤掉 {idx - last_idx - 1} 行无关日志) ...\n")
        result_lines.append(f"Line {idx + 1}: {lines[idx]}")
        last_idx = idx

    return "\n".join(result_lines)
