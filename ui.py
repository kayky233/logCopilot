"""
ui.py — LogPilot Streamlit UI 组件 (Phase 1: 用户隔离版)
"""
import os

import pandas as pd
import streamlit as st

import utils


def render_sidebar():
    """
    渲染侧边栏，集成所有配置项。
    Returns:
        api_key, base_url, model_name, enable_filter,
        filter_keywords, context_lines, path_prefix, enable_code_agent
    """
    with st.sidebar:
        st.title("🎛️ 故障判决控制台")

        # =========================================================
        # 1. 用户身份
        # =========================================================
        with st.container(border=True):
            col_u1, col_u2 = st.columns([3, 1])
            with col_u1:
                user_id = st.text_input(
                    "👤 当前用户",
                    value=st.session_state.get("user_id", "default"),
                    help="输入ID自动加载专属配置和工作空间",
                    key="uid_input",
                    label_visibility="collapsed",
                )
            with col_u2:
                st.write("")
                st.caption("🟢 在线")

            # 切换用户时初始化工作空间
            if user_id != st.session_state.get("user_id", "default"):
                st.session_state["user_id"] = user_id
                utils.init_environment(user_id)

            st.session_state["user_id"] = user_id
            user_config = utils.load_user_config(user_id)

            # 显示存储用量
            usage = utils.get_user_storage_usage(user_id)
            pct = min(100, int(usage["total_mb"] / usage["limit_mb"] * 100)) if usage["limit_mb"] > 0 else 0
            st.progress(pct / 100, text=f"💾 {usage['total_mb']}MB / {usage['limit_mb']}MB ({usage['file_count']} 文件)")

        st.caption("--- 🔧 高级能力配置 ---")

        # =========================================================
        # 2. 增强能力 (代码库 + 日志初筛)
        # =========================================================
        with st.expander("🛠️ 增强分析能力", expanded=False):
            st.markdown("**1. 本地代码库 (Agent)**")

            current_root = utils.load_codebase_root()
            new_root = st.text_input("本地代码根目录", value=current_root, placeholder="D:/Code/Project")

            current_prefix = utils.load_path_prefix()
            new_prefix = st.text_input(
                "剥离服务器路径前缀 (映射)",
                value=current_prefix,
                placeholder="/usr1/BoardSoftware_26B_Trunk/Source/",
                help="如果日志包含服务器绝对路径，填入公共前缀用于剥离映射。",
            )

            enable_code_agent = st.toggle(
                "启用代码审计 (Code Agent)",
                value=True,
                help="开启后，AI 将尝试读取本地代码库进行根因分析。关闭可加快速度。",
            )

            if st.button("💾 更新映射配置", key="btn_update_root"):
                r1, m1 = utils.save_codebase_root(new_root)
                r2, m2 = utils.save_path_prefix(new_prefix)
                if r1 and r2:
                    st.toast("✅ 代码库映射已更新", icon="🔗")
                    st.rerun()
                else:
                    st.error(f"保存失败: {m1} {m2}")

            st.divider()

            st.markdown("**2. 日志智能初筛**")
            enable_filter = st.toggle("启用初筛", value=False, help="仅提取关键报错行及其上下文")

            filter_keywords = []
            context_lines = 5
            if enable_filter:
                default_kws = "ERROR, FATAL, FAIL, EXCEPTION, TIMEOUT, 0x"
                kw_str = st.text_area("关键词 (逗号分隔)", value=default_kws, height=60, help="不区分大小写")
                normalized_str = kw_str.replace("，", ",")
                filter_keywords = [k.strip() for k in normalized_str.split(",") if k.strip()]
                context_lines = st.number_input("上下文行数", min_value=1, max_value=20, value=5)

        # =========================================================
        # 3. 知识库管理 (Prompt + 手册)
        # =========================================================
        with st.expander("🧠 知识库管理 (Prompt/手册)", expanded=False):
            st.caption("📝 **Prompt 规则定义**")
            sys_opts = [f"🤖 System: {d} 专家" for d in utils.DOMAINS]
            task_opts = ["📝 Task: 任务模板"]
            sel_opt = st.selectbox("选择 Prompt", sys_opts + task_opts, label_visibility="collapsed")

            layer, name = "", ""
            if "System" in sel_opt:
                layer = "SYSTEM"
                name = sel_opt.split(":")[1].strip().split(" ")[0]
            else:
                layer = "TASK"
                name = "default"

            curr_content = utils.load_prompt(layer, name)
            new_content = st.text_area("内容编辑", value=curr_content, height=150, key=f"ed_{layer}_{name}")
            c1, c2 = st.columns(2)

            if c1.button("💾 保存", key=f"sv_{layer}_{name}"):
                if utils.save_prompt(layer, name, new_content):
                    if layer == "TASK":
                        st.session_state["task_tpl"] = new_content
                    st.toast("Prompt 已保存", icon="💾")

            if c2.button("🔄 重置", key=f"rs_{layer}_{name}"):
                def_val = (
                    utils.INIT_SYSTEM_PROMPTS.get(name, utils.INIT_SYSTEM_PROMPTS["OTHER"])
                    if layer == "SYSTEM"
                    else utils.INIT_TASK_TEMPLATE
                )
                utils.save_prompt(layer, name, def_val)
                st.rerun()

            st.divider()

            # 手册管理
            st.caption("📚 **故障手册库**")
            dom = st.selectbox("选择领域", utils.DOMAINS, key="dom_sel")
            user_manual_dir = os.path.join(utils.get_user_manual_root(user_id), dom)

            up_m = st.file_uploader(
                f"上传至 {dom}",
                type=["md", "pdf", "docx", "txt"],
                accept_multiple_files=True,
                key=f"um_{dom}",
            )
            if up_m:
                utils.save_uploaded_manuals(up_m, dom, user_id)

            if os.path.exists(user_manual_dir):
                files = sorted(os.listdir(user_manual_dir))
                if files:
                    with st.popover(f"🗑️ 管理 {dom} 文件"):
                        del_files = st.multiselect("选择删除", files, key=f"del_{dom}")
                        if del_files and st.button("确认删除", key=f"btn_d_{dom}"):
                            utils.delete_files(user_manual_dir, del_files)
                            st.rerun()

            tree = utils.get_manuals_by_domain(user_id)
            cnt_str = " | ".join([f"{d}:{len(tree.get(d, []))}" for d in utils.DOMAINS if len(tree.get(d, [])) > 0])
            if cnt_str:
                st.caption(f"库存: {cnt_str}")

        # =========================================================
        # 4. 日志源管理
        # =========================================================
        with st.expander("🪵 日志源管理", expanded=True):
            up_l = st.file_uploader(
                "上传日志文件",
                type=["log", "txt", "xlsx", "csv"],
                accept_multiple_files=True,
                label_visibility="collapsed",
            )
            if up_l:
                utils.save_uploaded_logs(up_l, user_id)

            user_log_dir = utils.get_user_log_dir(user_id)
            if os.path.exists(user_log_dir):
                l_files = sorted(os.listdir(user_log_dir))
                if l_files:
                    with st.popover("🗑️ 删除日志文件"):
                        del_logs = st.multiselect("选择删除", l_files, key="del_logs")
                        if del_logs and st.button("确认删除", key="btn_del_logs"):
                            utils.delete_files(user_log_dir, del_logs)
                            st.rerun()
                    st.caption(f"当前库存: {len(l_files)} 个文件")

        # =========================================================
        # 5. 底部：API 连接
        # =========================================================
        st.divider()
        with st.expander("⚙️ API 连接配置", expanded=False):
            b_url = st.text_input("Base URL", value=user_config["base_url"], key="k_url")
            m_name = st.text_input("Model Name", value=user_config["model_name"], key="k_model")
            a_key = st.text_input("API Key", value=user_config["api_key"], type="password", key="k_key")

            if st.button("💾 保存所有配置", key="btn_save_all", type="primary", use_container_width=True):
                if utils.save_user_config(user_id, {"base_url": b_url, "model_name": m_name, "api_key": a_key}):
                    st.toast("配置已保存", icon="✅")

            col_a, col_b = st.columns(2)
            if col_a.button("🧹 清空我的数据", key="btn_cls"):
                utils.clear_user_workspace(user_id)
                st.rerun()
            if col_b.button("🗑️ 清空缓存", key="btn_cache"):
                utils.cache_clear()
                st.toast("缓存已清空", icon="🗑️")

        return a_key, b_url, m_name, enable_filter, filter_keywords, context_lines, new_prefix, enable_code_agent


def render_selectors(manual_tree, log_files):
    """主界面选择器"""
    c1, c2 = st.columns([3, 2])
    sel_mans = []
    sel_logs = []

    with c1:
        st.markdown("##### 1. 选择排查场景")
        if not any(manual_tree.values()):
            st.info("👈 请在左侧上传手册")
        else:
            for d in utils.DOMAINS:
                files = manual_tree.get(d, [])
                if not files:
                    continue
                with st.expander(f"📂 {d} ({len(files)})", expanded=(d == utils.DOMAINS[0])):
                    all_c = st.checkbox("全选", key=f"all_{d}")
                    df = pd.DataFrame({"启用": [all_c] * len(files), "文件名": files})
                    res = st.data_editor(
                        df,
                        column_config={
                            "启用": st.column_config.CheckboxColumn(width="small"),
                            "文件名": st.column_config.TextColumn(disabled=True),
                        },
                        hide_index=True,
                        use_container_width=True,
                        key=f"tbl_{d}",
                    )
                    for f in res[res["启用"]]["文件名"]:
                        sel_mans.append({"domain": d, "file": f})

    with c2:
        st.markdown("##### 2. 选择日志")
        if not log_files:
            st.info("👈 请在左侧上传日志")
        else:
            cont = st.container(border=True)
            if cont.checkbox("全选日志", value=True):
                sel_logs = log_files
            else:
                sel_logs = cont.multiselect("选择日志", log_files, label_visibility="collapsed")

    btn = st.button(
        f"🚀 扫描 {len(sel_logs)} 日志 × {len(sel_mans)} 场景",
        type="primary",
        use_container_width=True,
        disabled=(not sel_mans or not sel_logs),
    )
    return sel_mans, sel_logs, btn


def render_result_card(box, info, res, trace_data=None):
    """渲染结果卡片"""
    dom, file = info["domain"], info["file"]
    icon = {"BSP": "💻", "CLK": "⏰", "SWITCH": "🔌"}.get(dom, "📄")

    if res["is_fault"]:
        box.error(f"🔴 **[{dom}] {file}**")
        st.markdown(f"**诊断**: {res['title']} (Conf: {res['confidence']}%)")
        with st.popover("📄 查看详细报告"):
            st.markdown(f"### {icon} 领域专家诊断")
            st.info(f"**证据**: {res['reason']}")
            st.success(f"**建议**: {res['fix']}")
    elif res["title"] == "调用异常":
        box.warning(f"⚠️ {res['reason']}")
    else:
        box.success(f"🟢 **[{dom}] {file}**")

    if trace_data:
        with st.expander("🔍 维测：AI 思考过程 (Trace)", expanded=False):
            st.markdown("#### 1. 模型原始回复 (Raw)")
            st.code(trace_data.get("raw_response", "无内容"), language="json")

            steps = trace_data.get("steps", [])
            tools = trace_data.get("tool_calls", [])

            if steps:
                st.markdown(f"#### 2. 协作步骤 ({len(steps)}步)")
                for s in steps:
                    st.text(f"👣 {s}")
                if trace_data.get("log_summary"):
                    with st.popover("🕵️‍♂️ 查看 Log Agent 摘要"):
                        st.code(trace_data["log_summary"], language="json")
                if trace_data.get("code_insight"):
                    with st.popover("💻 查看 Code Agent 分析"):
                        st.markdown(trace_data["code_insight"])
            elif tools:
                st.markdown(f"#### 2. 工具调用 ({len(tools)}次)")
                for t in tools:
                    st.info(f"🔧 调用: `{t['func']}`\n📂 参数: `{t['args']}`")
                    st.text_area("结果片段", t["output"], height=100)

            st.markdown("#### 3. 完整输入上下文 (Full Context)")
            full_input = trace_data.get("final_input") or trace_data.get("prompt_input", "")
            st.caption(f"📏 总字符数: {len(full_input)} (这是 Boss Agent 实际看到的最终输入)")
            st.code(full_input, language="markdown")
