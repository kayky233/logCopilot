import json
import os
import shutil

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
LOG_DIR = os.path.join(BASE_DIR, "logs")
MANUAL_ROOT_DIR = os.path.join(BASE_DIR, "manuals")
PROMPT_DIR = "prompts"
CONFIG_DIR = "user_configs"

# 新增：代码库与路径映射配置
CODEBASE_CONFIG_PATH = os.path.join(CONFIG_DIR, "codebase_path.txt")
PATH_MAP_CONFIG_PATH = os.path.join(CONFIG_DIR, "path_mapping.txt")

# 领域定义
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
# 3. 初始化与环境构建
# ==========================================
def init_environment():
    """初始化目录并生成默认 Prompt 文件"""
    for d in [BASE_DIR, LOG_DIR, PROMPT_DIR, MANUAL_ROOT_DIR, CONFIG_DIR]:
        if not os.path.exists(d):
            os.makedirs(d)

    # 初始化领域目录 & System Prompts
    for domain in DOMAINS:
        # 1. 手册目录
        d_path = os.path.join(MANUAL_ROOT_DIR, domain)
        if not os.path.exists(d_path):
            os.makedirs(d_path)

        # 2. System Prompt 文件
        sys_path = os.path.join(PROMPT_DIR, f"system_{domain}.md")
        if not os.path.exists(sys_path):
            with open(sys_path, "w", encoding="utf-8") as f:
                f.write(INIT_SYSTEM_PROMPTS.get(domain, INIT_SYSTEM_PROMPTS["OTHER"]))

    # 生成默认 Task Template
    task_path = os.path.join(PROMPT_DIR, "task_default.md")
    if not os.path.exists(task_path):
        with open(task_path, "w", encoding="utf-8") as f:
            f.write(INIT_TASK_TEMPLATE)


def clear_workspace():
    """清空工作数据 (保留配置和Prompt)"""
    if os.path.exists(BASE_DIR):
        shutil.rmtree(BASE_DIR)
    init_environment()

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

    # Fallback
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
    safe_id = "".join([c for c in user_id if c.isalnum() or c in "_-"]) or "default"
    return os.path.join(CONFIG_DIR, f"config_{safe_id}.json")


def load_user_config(user_id):
    path = get_config_path(user_id)
    default = {
        "base_url": "http://api.openai.rnd.huawei.com/v1",
        "model_name": "gpt-oss-120b",
        "api_key": "sk-dummy",
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
    """加载代码库根路径"""
    if os.path.exists(CODEBASE_CONFIG_PATH):
        with open(CODEBASE_CONFIG_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def save_codebase_root(path):
    """保存代码库根路径"""
    try:
        with open(CODEBASE_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(path.strip())
        return True, "已保存"
    except Exception as e:
        return False, str(e)


def load_path_prefix():
    """加载需要剥离的服务器路径前缀"""
    if os.path.exists(PATH_MAP_CONFIG_PATH):
        with open(PATH_MAP_CONFIG_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def save_path_prefix(prefix):
    """保存路径前缀配置"""
    try:
        with open(PATH_MAP_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(prefix.strip())
        return True, "已保存"
    except Exception as e:
        return False, str(e)

# ==========================================
# 7. 文件 IO 与解析 (保留单一实现)
# ==========================================
def load_file_content(filepath):
    """
    通用文件读取器：支持 .md, .txt, .log, .xlsx, .csv, .docx, .pdf
    """
    try:
        ext = os.path.splitext(filepath)[1].lower()

        # 1. Excel 处理
        if ext in [".xlsx", ".xls"]:
            return pd.read_excel(filepath).astype(str).agg(" ".join, axis=1).str.cat(sep="\n")

        # 2. CSV 处理
        if ext == ".csv":
            try:
                df = pd.read_csv(filepath, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(filepath, encoding="gbk")
            return df.astype(str).agg(" ".join, axis=1).str.cat(sep="\n")

        # 3. Word 处理
        if ext == ".docx":
            if docx is None:
                return "❌ 错误: 未安装 python-docx 库"
            doc = docx.Document(filepath)
            return "\n".join([para.text for para in doc.paragraphs])

        # 4. PDF 处理
        if ext == ".pdf":
            if PdfReader is None:
                return "❌ 错误: 未安装 pypdf 库"
            reader = PdfReader(filepath)
            return "\n".join([page.extract_text() for page in reader.pages])

        # 5. 纯文本处理
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"❌ 文件解析失败 ({os.path.basename(filepath)}): {str(e)}"


def get_manuals_by_domain():
    tree = {}
    for d in DOMAINS:
        path = os.path.join(MANUAL_ROOT_DIR, d)
        if os.path.exists(path):
            tree[d] = sorted(
                [f for f in os.listdir(path) if f.lower().endswith((".md", ".pdf", ".docx", ".txt"))]
            )
    return tree


def save_uploaded_manuals(uploaded_files, domain):
    target_dir = os.path.join(MANUAL_ROOT_DIR, domain)
    os.makedirs(target_dir, exist_ok=True)
    for f in uploaded_files:
        with open(os.path.join(target_dir, f.name), "wb") as out_f:
            out_f.write(f.getbuffer())
    st.toast(f"✅ {len(uploaded_files)} 个手册已上传至 {domain}", icon="📚")


def save_uploaded_logs(uploaded_files):
    os.makedirs(LOG_DIR, exist_ok=True)
    for f in uploaded_files:
        with open(os.path.join(LOG_DIR, f.name), "wb") as out_f:
            out_f.write(f.getbuffer())
    st.toast(f"✅ {len(uploaded_files)} 个日志已上传", icon="🪵")


def delete_files(dir_path, filenames):
    for f in filenames:
        try:
            os.remove(os.path.join(dir_path, f))
        except Exception:
            pass
    st.toast(f"🗑️ 已删除 {len(filenames)} 个文件", icon="🧹")

# ==========================================
# 8. 日志处理工具
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
    """
    关键日志初筛算法 (优化版: 基于索引集去重):
    1. 扫描所有行，找到包含 keywords 的行。
    2. 针对每一个命中行，将其 前N行 和 后N行 的索引加入集合。
    3. 对集合排序，提取内容。
    4. 如果行号不连续，插入分隔符。
    """
    if not content or not keywords:
        return content

    lines = content.splitlines()
    total_lines = len(lines)
    keep_indices = set()

    valid_keywords = [k.lower().strip() for k in keywords if k.strip()]
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

