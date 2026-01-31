import os
import traceback
import warnings

import streamlit as st

import ui
import utils
from client import FaultDetectorClient

# ==============================================================================
# 1. 初始化 & 全局配置
# ==============================================================================
st.set_page_config(page_title="LogPilot", layout="wide", page_icon="📡")

# 只保留 Python 原生的警告压制
warnings.filterwarnings("ignore")

utils.init_environment()

if "task_tpl" not in st.session_state:
    st.session_state["task_tpl"] = utils.load_prompt("TASK", "default")

# ==============================================================================
# 2. 侧边栏配置
# ==============================================================================
api_key, base_url, model_name, enable_filter, manual_keywords, context_lines, path_prefix, enable_code_agent = (
    ui.render_sidebar()
)

# ==============================================================================
# 3. 主界面 & 状态栏
# ==============================================================================
st.title("📡 基站故障深度判决系统 (v3.0)")

badges = []
badges.append(f"🤖 模型:{model_name}")
badges.append("🔍 初筛:ON" if enable_filter else "⚪ 初筛:OFF")

codebase = utils.load_codebase_root()
if codebase:
    code_status = "✅" if enable_code_agent else "⏸️"
    badges.append(f"{code_status} 代码库:{os.path.basename(codebase)}")
else:
    badges.append("⚪ 代码库:未挂载")

st.caption(" | ".join(badges))

manual_tree = utils.get_manuals_by_domain()
log_files = sorted(os.listdir(utils.LOG_DIR)) if os.path.exists(utils.LOG_DIR) else []

sel_mans, sel_logs, start_btn = ui.render_selectors(manual_tree, log_files)

# ==============================================================================
# 4. 执行核心逻辑
# ==============================================================================
if start_btn:
    st.divider()

    # API Key 强力清洗 (防止复制粘贴带入空格/换行)
    if api_key:
        api_key = str(api_key).strip()

    # 宽松校验，允许短 Key (测试用)
    if not api_key:
        st.error("❌ API Key 为空！")
        st.info("💡 提示：请在左侧侧边栏填入 Key。")
        st.stop()

    # 初始化客户端
    try:
        detector = FaultDetectorClient(api_key, base_url, model_name)
    except Exception as e:
        st.error(f"❌ 客户端初始化失败: {e}")
        st.stop()

    st.subheader("📊 诊断看板")
    bar = st.progress(0)
    total = len(sel_logs) * len(sel_mans)
    done = 0

    for log in sel_logs:
        path = os.path.join(utils.LOG_DIR, log)
        raw_content = utils.load_file_content(path)
        raw_len = len(raw_content)

        with st.expander(f"📄 日志源: {log}", expanded=True):
            cols = st.columns(3)
            for i, info in enumerate(sel_mans):
                dom, file = info["domain"], info["file"]
                with cols[i % 3]:
                    box = st.empty()
                    try:
                        box.info(f"⏳ [{dom}] 正在解析手册...")
                        m_text = utils.load_file_content(os.path.join(utils.MANUAL_ROOT_DIR, dom, file))

                        # 强制特征提取 (逻辑闭环核心)
                        auto_keywords = detector.get_search_keywords(m_text)
                        final_keywords = list(set(auto_keywords + manual_keywords))

                        if final_keywords:
                            st.caption(f"🗝️ AI 提取特征词: `{final_keywords[:5]}...`")

                        # 智能日志截取策略
                        filtered_log = ""
                        final_log_input = ""

                        # 策略A: 尝试降噪过滤 (开关开启 且 有特征词)
                        if enable_filter and final_keywords and raw_len > 0:
                            box.info(f"⏳ 正在基于 {len(final_keywords)} 个特征码过滤...")
                            filtered_log = utils.filter_log_content(
                                raw_content, final_keywords, context_lines=context_lines
                            )

                        # 决策: 使用过滤后的内容 还是 原始截断
                        if filtered_log and "[System Filter]" not in filtered_log and len(filtered_log) > 100:
                            final_log_input = utils.get_smart_snippet(filtered_log, head=5000, tail=5000)
                            st.caption(f"📉 **降噪生效**: 命中 {len(filtered_log)} 字符关键信息")
                        else:
                            if enable_filter:
                                st.toast(
                                    f"⚠️ [{dom}] 关键词未命中，降级为首尾截断模式。",
                                    icon="⚠️",
                                )
                            # 兜底: 取 Head + Tail，确保读到日志末尾的 Fatal Error
                            final_log_input = utils.get_smart_snippet(raw_content, head=3000, tail=5000)

                        if not final_log_input.strip():
                            st.error("日志内容为空，跳过分析。")
                            continue

                        # Pipeline 调用
                        box.info(f"🤖 [{dom}] 深鉴 Multi-Agent 启动...")
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

                        # 错误检查
                        log_summary = trace_data.get("log_summary", "")
                        if "Agent Error" in log_summary or not log_summary:
                            st.error("🛑 Log Agent 遭遇通信阻断/报错")
                            st.markdown("👇 **服务器返回的原始错误信息**:")
                            st.code(log_summary if log_summary else "(空响应)", language="text")

                        # 正常渲染
                        if trace_data and "steps" in trace_data:
                            state_icon = "✅" if res.get("is_fault") else "ℹ️"
                            with st.status(f"{state_icon} 多智能体协作完成", expanded=False):
                                for step in trace_data["steps"]:
                                    st.write(step)
                                if trace_data.get("code_insight"):
                                    st.markdown("---")
                                    st.markdown(
                                        f"**💻 代码审计结果:**\n{trace_data['code_insight'][:200]}..."
                                    )

                        ui.render_result_card(box, info, res, trace_data)

                    except Exception as e:
                        box.error(f"❌ 运行时异常: {str(e)}")
                        with st.expander("🛠️ 查看技术堆栈 (发给开发者)"):
                            st.code(traceback.format_exc())

                done += 1
                bar.progress(done / total)

    st.balloons()
    st.success("✅ 全局智能巡检完成")

