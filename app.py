"""
app.py — LogPilot 主程序 (v4.0 UI 优化版)
"""
import json
import os
import time
import traceback
import warnings

import streamlit as st

import ui
import utils
from client import FaultDetectorClient

# ==============================================================================
# 1. 初始化
# ==============================================================================
st.set_page_config(page_title="LogPilot", layout="wide", page_icon="📡")
warnings.filterwarnings("ignore")

# 注入自定义样式
ui.inject_custom_css()

# Session State
if "user_id" not in st.session_state:
    st.session_state["user_id"] = "default"

user_id = st.session_state.get("user_id", "default")
utils.init_environment(user_id)

if "task_tpl" not in st.session_state:
    st.session_state["task_tpl"] = utils.load_prompt("TASK", "default")

# ==============================================================================
# 2. 侧边栏
# ==============================================================================
api_key, base_url, model_name, enable_filter, manual_keywords, context_lines, path_prefix, enable_code_agent = (
    ui.render_sidebar()
)
user_id = st.session_state.get("user_id", "default")

# ==============================================================================
# 3. 主界面 Hero 区域
# ==============================================================================
st.markdown("""
<div class="hero-title">LogPilot</div>
<div class="hero-sub">Multi-Agent AI 驱动 · 基站故障深度判决系统</div>
""", unsafe_allow_html=True)

# 顶部状态指标
ui.render_metrics_header(user_id, model_name, enable_filter, enable_code_agent)

st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)

# ==============================================================================
# 4. 选择器
# ==============================================================================
manual_tree = utils.get_manuals_by_domain(user_id)
user_log_dir = utils.get_user_log_dir(user_id)
log_files = sorted(os.listdir(user_log_dir)) if os.path.exists(user_log_dir) else []

sel_mans, sel_logs, start_btn = ui.render_selectors(manual_tree, log_files, user_log_dir)

# ==============================================================================
# 5. 执行分析
# ==============================================================================
if start_btn:
    st.divider()

    # 校验 API Key
    if api_key:
        api_key = str(api_key).strip()
    if not api_key:
        st.error("❌ 请先在左侧「⚡ API 连接」中填入 API Key")
        st.stop()

    # 初始化客户端
    try:
        detector = FaultDetectorClient(api_key, base_url, model_name)
    except Exception as e:
        st.error(f"❌ 客户端初始化失败: {e}")
        st.stop()

    # 进度条
    total = len(sel_logs) * len(sel_mans)
    bar = st.progress(0, text="🚀 正在初始化分析引擎...")
    done = 0
    all_results = []
    start_time = time.time()

    codebase = utils.load_codebase_root()

    for log in sel_logs:
        path = os.path.join(user_log_dir, log)
        raw_content = utils.load_file_content(path)
        raw_len = len(raw_content)

        with st.expander(f"📄 {log}  ({raw_len:,} 字符)", expanded=True):
            cols = st.columns(min(3, len(sel_mans)) if sel_mans else 1)

            for i, info in enumerate(sel_mans):
                dom, file = info["domain"], info["file"]
                with cols[i % len(cols)]:
                    box = st.container()

                    try:
                        # 1. 读取手册
                        bar.progress(done / total, text=f"📚 [{dom}] 正在解析手册: {file}...")
                        m_path = utils.resolve_manual_path(user_id, dom, file)
                        m_text = utils.load_file_content(m_path)

                        # 2. 特征词提取 (带缓存)
                        cached_kw = utils.cache_get("keywords", m_text[:5000])
                        if cached_kw:
                            try:
                                auto_keywords = json.loads(cached_kw)
                            except Exception:
                                auto_keywords = []
                        else:
                            auto_keywords = detector.get_search_keywords(m_text)
                            utils.cache_set("keywords", json.dumps(auto_keywords, ensure_ascii=False), m_text[:5000])

                        final_keywords = list(set(auto_keywords + manual_keywords))

                        # 3. 日志预处理
                        bar.progress(done / total, text=f"🔍 [{dom}] 日志预处理...")
                        filtered_log = ""
                        final_log_input = ""

                        if enable_filter and final_keywords and raw_len > 0:
                            filtered_log = utils.filter_log_content(
                                raw_content, final_keywords, context_lines=context_lines
                            )

                        if filtered_log and "[System Filter]" not in filtered_log and len(filtered_log) > 100:
                            final_log_input = utils.get_smart_snippet(filtered_log, head=5000, tail=5000)
                        else:
                            final_log_input = utils.get_smart_snippet(raw_content, head=3000, tail=5000)

                        if not final_log_input.strip():
                            box.warning("日志内容为空，跳过分析。")
                            continue

                        # 4. Pipeline
                        bar.progress(done / total, text=f"🤖 [{dom}] Multi-Agent 分析中...")
                        sys_p = utils.load_prompt("SYSTEM", dom)
                        task_p = st.session_state["task_tpl"]

                        res, trace_data = detector.analyze(
                            manual_content=m_text,
                            log_content=final_log_input,
                            sys_prompt=sys_p,
                            user_tpl=task_p,
                            codebase_root=codebase,
                            server_path_prefix=path_prefix,
                            enable_code_agent=enable_code_agent,
                            focus_keywords=final_keywords,
                        )

                        # 5. 渲染结果
                        ui.render_result_card(box, info, res, trace_data)
                        all_results.append(res)

                    except Exception as e:
                        box.error(f"❌ 运行异常: {str(e)}")
                        with st.expander("🛠️ 技术堆栈"):
                            st.code(traceback.format_exc())
                        all_results.append({"is_fault": False, "confidence": 0, "title": "调用异常",
                                            "reason": str(e), "fix": ""})

                done += 1
                bar.progress(done / total, text=f"✅ 已完成 {done}/{total}")

    # 完成
    elapsed = time.time() - start_time
    bar.progress(1.0, text=f"✅ 全部完成！耗时 {elapsed:.1f}s")

    st.divider()
    st.markdown("### 📊 扫描汇总")
    ui.render_scan_dashboard(all_results)

    st.balloons()
