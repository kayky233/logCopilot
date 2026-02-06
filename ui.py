"""
ui.py — LogPilot UI 组件 (v5.0 大规模文件优化版)
"""
import fnmatch
import os

import streamlit as st

import utils

# 每页显示条数
PAGE_SIZE = 20


# =========================================================================
# 0. 全局样式注入
# =========================================================================
def inject_custom_css():
    """注入自定义 CSS"""
    st.markdown("""
    <style>
    /* ---- 全局 ---- */
    .block-container { padding-top: 2rem; }

    /* ---- Hero ---- */
    .hero-title {
        font-size: 2.2rem; font-weight: 800;
        background: linear-gradient(135deg, #4F8BF9 0%, #7C3AED 50%, #EC4899 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0.1rem; letter-spacing: -0.5px;
    }
    .hero-sub { color: #9CA3AF; font-size: 0.92rem; margin-bottom: 1.5rem; }

    /* ---- 徽章 ---- */
    .status-badge {
        display: inline-block; padding: 3px 10px; border-radius: 20px;
        font-size: 0.75rem; font-weight: 600; margin-right: 6px; margin-bottom: 6px;
    }
    .badge-blue   { background:#1E3A5F; color:#60A5FA; border:1px solid #2563EB40; }
    .badge-green  { background:#14332A; color:#34D399; border:1px solid #05966940; }
    .badge-amber  { background:#332B14; color:#FBBF24; border:1px solid #D9770640; }
    .badge-gray   { background:#1F2937; color:#9CA3AF; border:1px solid #4B556340; }
    .badge-purple { background:#2D1B4E; color:#A78BFA; border:1px solid #7C3AED40; }

    /* ---- 步骤指示器 ---- */
    .step-header {
        display: flex; align-items: center; gap: 10px;
        margin-bottom: 12px; padding-bottom: 8px;
        border-bottom: 1px solid #1F2937;
    }
    .step-num {
        width: 28px; height: 28px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.82rem; font-weight: 700; color: #fff; flex-shrink: 0;
    }
    .step-num.active   { background: #4F8BF9; }
    .step-num.inactive { background: #374151; }
    .step-label { font-size: 1rem; font-weight: 600; color: #E5E7EB; }
    .step-count { font-size: 0.78rem; color: #6B7280; margin-left: auto; }

    /* ---- 搜索栏 ---- */
    .search-row {
        display: flex; align-items: center; gap: 8px;
        padding: 8px 12px; background: #111827;
        border: 1px solid #1F2937; border-radius: 10px;
        margin-bottom: 10px;
    }

    /* ---- 文件行 ---- */
    .file-row {
        display: flex; align-items: center; gap: 8px;
        padding: 7px 12px; margin: 2px 0; border-radius: 8px;
        font-size: 0.82rem; cursor: pointer;
        transition: all 0.15s ease;
        border: 1px solid transparent;
    }
    .file-row:hover { background: #1A1F2E; }
    .file-row.selected {
        background: #1E3A5F18; border-color: #2563EB40;
    }
    .file-name { flex: 1; color: #D1D5DB; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .file-size { color: #6B7280; font-size: 0.72rem; flex-shrink: 0; }
    .file-domain {
        font-size: 0.68rem; padding: 1px 6px; border-radius: 4px;
        background: #1F2937; color: #9CA3AF; flex-shrink: 0;
    }

    /* ---- 已选摘要 ---- */
    .sel-summary {
        background: linear-gradient(135deg, #111827 0%, #0D1117 100%);
        border: 1px solid #1F2937; border-radius: 10px;
        padding: 12px 16px; margin: 10px 0;
    }
    .sel-summary-row {
        display: flex; justify-content: space-between; align-items: center;
    }
    .sel-tag {
        display: inline-block; padding: 2px 8px; border-radius: 12px;
        font-size: 0.72rem; font-weight: 600; margin-right: 4px;
        background: #1E3A5F; color: #60A5FA; border: 1px solid #2563EB30;
    }

    /* ---- 指标卡片 ---- */
    .metric-row { display: flex; gap: 12px; margin-bottom: 1.2rem; flex-wrap: wrap; }
    .metric-card {
        flex: 1; min-width: 120px;
        background: linear-gradient(135deg, #1A1F2E 0%, #111827 100%);
        border: 1px solid #374151; border-radius: 12px;
        padding: 16px 18px; text-align: center; transition: all 0.2s ease;
    }
    .metric-card:hover { border-color: #4F8BF9; box-shadow: 0 0 20px rgba(79,139,249,0.1); transform: translateY(-1px); }
    .metric-value { font-size: 1.7rem; font-weight: 700; color: #F9FAFB; line-height: 1.2; }
    .metric-label { font-size: 0.78rem; color: #6B7280; margin-top: 4px; }
    .metric-value.fault { color: #F87171; }
    .metric-value.ok    { color: #34D399; }
    .metric-value.warn  { color: #FBBF24; }

    /* ---- 结果卡片 ---- */
    .result-card {
        border-radius: 12px; padding: 20px; margin-bottom: 12px;
        border-left: 4px solid; transition: all 0.2s ease;
    }
    .result-card:hover { transform: translateX(2px); }
    .result-card.fault { background: linear-gradient(135deg,#1C1012 0%,#0E1117 100%); border-left-color:#EF4444; }
    .result-card.ok    { background: linear-gradient(135deg,#0D1912 0%,#0E1117 100%); border-left-color:#10B981; }
    .result-card.error { background: linear-gradient(135deg,#1C1712 0%,#0E1117 100%); border-left-color:#F59E0B; }
    .result-title { font-size: 1.1rem; font-weight: 700; margin-bottom: 6px; }

    /* ---- 置信度条 ---- */
    .conf-bar-bg { background:#1F2937; border-radius:6px; height:8px; width:100%; overflow:hidden; margin:6px 0; }
    .conf-bar-fill { height:100%; border-radius:6px; transition: width 0.5s ease; }
    .conf-high { background: linear-gradient(90deg,#EF4444,#F87171); }
    .conf-mid  { background: linear-gradient(90deg,#F59E0B,#FBBF24); }
    .conf-low  { background: linear-gradient(90deg,#6B7280,#9CA3AF); }

    /* ---- Pipeline 步骤 ---- */
    .step-item {
        display:flex; align-items:flex-start; gap:10px;
        padding:8px 0; border-left:2px solid #374151;
        padding-left:16px; margin-left:8px; position:relative;
    }
    .step-item::before {
        content:''; position:absolute; left:-5px; top:12px;
        width:8px; height:8px; border-radius:50%; background:#4F8BF9;
    }
    .step-text { font-size:0.85rem; color:#D1D5DB; }

    /* ---- 侧边栏 ---- */
    section[data-testid="stSidebar"] { background: linear-gradient(180deg,#0D1117 0%,#111827 100%); }

    /* ---- 空状态 ---- */
    .empty-state { text-align:center; padding:2.5rem 2rem; color:#6B7280; }
    .empty-state .icon { font-size:2.5rem; margin-bottom:0.8rem; }
    .empty-state .title { font-size:1rem; font-weight:600; color:#9CA3AF; }
    .empty-state .desc { font-size:0.82rem; margin-top:0.4rem; }

    /* ---- 任务矩阵 ---- */
    .task-matrix {
        display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px;
    }
    .task-chip {
        padding: 3px 8px; border-radius: 6px; font-size: 0.7rem;
        background: #1A1F2E; border: 1px solid #374151; color: #9CA3AF;
    }
    .task-chip.active {
        background: #1E3A5F20; border-color: #2563EB40; color: #60A5FA;
    }

    /* ---- 加载更多按钮 ---- */
    .load-more-hint {
        text-align: center; padding: 8px; font-size: 0.78rem; color: #6B7280;
    }

    /* ---- 隐藏默认 ---- */
    #MainMenu {visibility:hidden;} footer {visibility:hidden;} header {visibility:hidden;}
    </style>
    """, unsafe_allow_html=True)


# =========================================================================
# 1. 侧边栏
# =========================================================================
def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; padding: 0.5rem 0 1rem 0;">
            <div style="font-size:2.5rem;">📡</div>
            <div style="font-size:1.2rem; font-weight:700; color:#F9FAFB;">LogPilot</div>
            <div style="font-size:0.72rem; color:#6B7280;">基站故障深度判决系统 v5.0</div>
        </div>
        """, unsafe_allow_html=True)

        # ── 用户身份卡 ──
        with st.container(border=True):
            user_id = st.text_input(
                "👤 用户 ID", value=st.session_state.get("user_id", "default"),
                help="切换用户加载独立工作空间", key="uid_input", placeholder="工号或姓名",
            )
            if user_id != st.session_state.get("user_id", "default"):
                st.session_state["user_id"] = user_id
                utils.init_environment(user_id)
            st.session_state["user_id"] = user_id
            user_config = utils.load_user_config(user_id)

            usage = utils.get_user_storage_usage(user_id)
            pct = min(100, int(usage["total_mb"] / usage["limit_mb"] * 100)) if usage["limit_mb"] > 0 else 0
            bar_color = "#10B981" if pct < 70 else "#F59E0B" if pct < 90 else "#EF4444"
            st.markdown(f"""
            <div style="margin-top:4px;">
                <div style="display:flex; justify-content:space-between; font-size:0.72rem; color:#6B7280;">
                    <span>💾 存储</span>
                    <span>{usage['total_mb']}MB / {usage['limit_mb']}MB · {usage['file_count']} 文件</span>
                </div>
                <div style="background:#1F2937; border-radius:4px; height:4px; margin-top:3px; overflow:hidden;">
                    <div style="width:{pct}%; height:100%; background:{bar_color}; border-radius:4px;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ── API 连接 ──
        with st.expander("⚡ API 连接", expanded=not bool(user_config.get("api_key"))):
            b_url = st.text_input("Base URL", value=user_config["base_url"], key="k_url",
                                  placeholder="https://api.deepseek.com/v1")
            m_name = st.text_input("模型", value=user_config["model_name"], key="k_model",
                                   placeholder="deepseek-chat")
            a_key = st.text_input("API Key", value=user_config["api_key"], type="password", key="k_key",
                                  placeholder="sk-...")
            if st.button("💾 保存配置", key="btn_save_all", type="primary", use_container_width=True):
                if utils.save_user_config(user_id, {"base_url": b_url, "model_name": m_name, "api_key": a_key}):
                    st.toast("✅ 配置已保存", icon="💾")

        # ── 日志源 ──
        with st.expander("📂 日志源", expanded=True):
            up_l = st.file_uploader("上传日志", type=["log", "txt", "xlsx", "csv"],
                                    accept_multiple_files=True, label_visibility="collapsed", key="upload_logs")
            if up_l:
                utils.save_uploaded_logs(up_l, user_id)
            user_log_dir = utils.get_user_log_dir(user_id)
            if os.path.exists(user_log_dir):
                l_files = sorted(os.listdir(user_log_dir))
                if l_files:
                    st.caption(f"已有 {len(l_files)} 个日志文件")
                    with st.popover("🗑️ 管理文件"):
                        del_logs = st.multiselect("选择删除", l_files, key="del_logs")
                        if del_logs and st.button("确认删除", key="btn_del_logs", type="primary"):
                            utils.delete_files(user_log_dir, del_logs)
                            st.rerun()

        # ── 故障手册 ──
        with st.expander("📚 故障手册库", expanded=False):
            dom = st.selectbox("领域", utils.DOMAINS, key="dom_sel", label_visibility="collapsed")
            user_manual_dir = os.path.join(utils.get_user_manual_root(user_id), dom)
            up_m = st.file_uploader(f"上传至 {dom}", type=["md", "pdf", "docx", "txt"],
                                    accept_multiple_files=True, key=f"um_{dom}", label_visibility="collapsed")
            if up_m:
                utils.save_uploaded_manuals(up_m, dom, user_id)

            tree = utils.get_manuals_by_domain(user_id)
            total_manuals = sum(len(v) for v in tree.values())
            if total_manuals > 0:
                counts = [f"{d}:{len(tree.get(d, []))}" for d in utils.DOMAINS if tree.get(d)]
                st.caption(f"库存: {' · '.join(counts)}")
                if os.path.exists(user_manual_dir):
                    files = sorted(os.listdir(user_manual_dir))
                    if files:
                        with st.popover(f"🗑️ 管理 {dom}"):
                            del_files = st.multiselect("选择删除", files, key=f"del_{dom}")
                            if del_files and st.button("确认删除", key=f"btn_d_{dom}", type="primary"):
                                utils.delete_files(user_manual_dir, del_files)
                                st.rerun()

        # ── 高级设置 ──
        with st.expander("🔬 高级设置", expanded=False):
            st.markdown("**日志智能初筛**")
            enable_filter = st.toggle("启用关键词初筛", value=False,
                                      help="仅提取匹配关键词的日志行及上下文")
            filter_keywords = []
            context_lines = 5
            if enable_filter:
                kw_str = st.text_area("关键词", value="ERROR, FATAL, FAIL, EXCEPTION, TIMEOUT, 0x",
                                      height=60, help="逗号分隔")
                filter_keywords = [k.strip() for k in kw_str.replace("，", ",").split(",") if k.strip()]
                context_lines = st.slider("上下文行数", 1, 20, 5)

            st.divider()
            st.markdown("**代码库挂载**")
            current_root = utils.load_codebase_root()
            new_root = st.text_input("代码根目录", value=current_root, placeholder="D:/Code/Project")
            current_prefix = utils.load_path_prefix()
            new_prefix = st.text_input("服务器路径前缀", value=current_prefix,
                                       placeholder="/usr1/BoardSoftware/Source/")
            enable_code_agent = st.toggle("启用 Code Agent", value=True)
            if st.button("保存代码库配置", key="btn_code_cfg", use_container_width=True):
                utils.save_codebase_root(new_root)
                utils.save_path_prefix(new_prefix)
                st.toast("✅ 代码库配置已保存")

            st.divider()
            st.markdown("**Prompt 工程**")
            sys_opts = [f"System: {d}" for d in utils.DOMAINS]
            task_opts = ["Task: 默认模板"]
            sel_opt = st.selectbox("编辑 Prompt", sys_opts + task_opts, key="prompt_sel",
                                   label_visibility="collapsed")
            layer = "SYSTEM" if "System" in sel_opt else "TASK"
            name = sel_opt.split(":")[1].strip() if "System" in sel_opt else "default"
            curr_content = utils.load_prompt(layer, name)
            new_content = st.text_area("Prompt", value=curr_content, height=120, key=f"ed_{layer}_{name}")
            pc1, pc2 = st.columns(2)
            if pc1.button("💾 保存", key=f"sv_{layer}_{name}", use_container_width=True):
                if utils.save_prompt(layer, name, new_content):
                    if layer == "TASK":
                        st.session_state["task_tpl"] = new_content
                    st.toast("Prompt 已保存", icon="💾")
            if pc2.button("🔄 重置", key=f"rs_{layer}_{name}", use_container_width=True):
                def_val = (utils.INIT_SYSTEM_PROMPTS.get(name, utils.INIT_SYSTEM_PROMPTS["OTHER"])
                           if layer == "SYSTEM" else utils.INIT_TASK_TEMPLATE)
                utils.save_prompt(layer, name, def_val)
                st.rerun()

        # ── 底部 ──
        st.divider()
        dc1, dc2 = st.columns(2)
        if dc1.button("🧹 清空数据", key="btn_cls", use_container_width=True):
            utils.clear_user_workspace(user_id)
            st.rerun()
        if dc2.button("🗑️ 清缓存", key="btn_cache", use_container_width=True):
            utils.cache_clear()
            st.toast("缓存已清空", icon="🗑️")

        return a_key, b_url, m_name, enable_filter, filter_keywords, context_lines, new_prefix, enable_code_agent


# =========================================================================
# 2. 主界面选择器 (v5.0 大规模文件优化)
# =========================================================================

def _init_selector_state():
    """初始化选择器所需的 session_state"""
    defaults = {
        "sel_manual_keys": set(),   # 已选手册: set of "domain||filename"
        "sel_log_keys": set(),      # 已选日志: set of filename
        "manual_search": "",
        "log_search": "",
        "manual_page": 1,
        "log_page": 1,
        "manual_domain_filter": "ALL",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _get_file_size_str(filepath: str) -> str:
    """获取文件大小的友好字符串"""
    try:
        size = os.path.getsize(filepath)
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.0f}KB"
        else:
            return f"{size / (1024 * 1024):.1f}MB"
    except Exception:
        return ""


def render_selectors(manual_tree, log_files, user_log_dir=""):
    """
    大规模文件选择器:
      - 上下布局 (Step 1 手册 → Step 2 日志)
      - 搜索过滤 + 领域 Tabs + 分页加载
      - 通配符批量选 + 已选摘要面板
      - 任务预估
    """
    _init_selector_state()

    # 构建扁平手册列表: [{domain, file, key}, ...]
    all_manuals = []
    for d in utils.DOMAINS:
        for f in manual_tree.get(d, []):
            all_manuals.append({"domain": d, "file": f, "key": f"{d}||{f}"})

    total_manuals = len(all_manuals)
    total_logs = len(log_files)

    # ============================================================
    # 空状态
    # ============================================================
    if total_manuals == 0 and total_logs == 0:
        st.markdown("""
        <div class="empty-state">
            <div class="icon">🚀</div>
            <div class="title">准备开始</div>
            <div class="desc">在左侧边栏上传「📚 故障手册」和「📂 日志文件」即可开始分析</div>
        </div>
        """, unsafe_allow_html=True)
        btn = st.button("🚀 请先上传文件", type="primary", use_container_width=True, disabled=True)
        return [], [], btn

    # ============================================================
    # Step 1: 选择排查手册
    # ============================================================
    st.markdown(f"""
    <div class="step-header">
        <div class="step-num {'active' if total_manuals > 0 else 'inactive'}">1</div>
        <div class="step-label">选择排查手册</div>
        <div class="step-count">{len(st.session_state['sel_manual_keys'])} / {total_manuals} 已选</div>
    </div>
    """, unsafe_allow_html=True)

    if total_manuals == 0:
        st.info("👈 请在左侧「📚 故障手册库」上传手册")
    else:
        # 搜索 + 领域筛选 + 操作栏
        fc1, fc2, fc3, fc4 = st.columns([4, 2, 1, 1])
        with fc1:
            manual_search = st.text_input(
                "搜索手册", key="m_search_input",
                placeholder=f"🔍 在 {total_manuals} 个手册中搜索...",
                label_visibility="collapsed",
            )
        with fc2:
            active_domains = ["ALL"] + [d for d in utils.DOMAINS if manual_tree.get(d)]
            domain_filter = st.selectbox("领域", active_domains, key="m_domain_filter",
                                         label_visibility="collapsed")
        with fc3:
            if st.button("全选", key="m_select_all", use_container_width=True):
                for m in all_manuals:
                    st.session_state["sel_manual_keys"].add(m["key"])
                st.rerun()
        with fc4:
            if st.button("清空", key="m_clear_all", use_container_width=True):
                st.session_state["sel_manual_keys"] = set()
                st.rerun()

        # 过滤
        filtered_manuals = all_manuals
        if domain_filter != "ALL":
            filtered_manuals = [m for m in filtered_manuals if m["domain"] == domain_filter]
        if manual_search.strip():
            q = manual_search.strip().lower()
            filtered_manuals = [m for m in filtered_manuals if q in m["file"].lower() or q in m["domain"].lower()]

        # 通配符批量选
        with st.popover("⚡ 批量选择"):
            pattern = st.text_input("通配符模式", placeholder="*pll*  或  manual_bsp*",
                                    key="m_batch_pattern", help="支持 * 和 ? 通配符")
            if pattern.strip():
                matched = [m for m in all_manuals
                           if fnmatch.fnmatch(m["file"].lower(), pattern.strip().lower())]
                st.caption(f"匹配 **{len(matched)}** / {total_manuals} 个手册")
                bc1, bc2 = st.columns(2)
                if bc1.button("选中匹配项", key="m_batch_add", use_container_width=True):
                    for m in matched:
                        st.session_state["sel_manual_keys"].add(m["key"])
                    st.rerun()
                if bc2.button("取消匹配项", key="m_batch_remove", use_container_width=True):
                    for m in matched:
                        st.session_state["sel_manual_keys"].discard(m["key"])
                    st.rerun()

        # 分页显示
        if f"manual_page" not in st.session_state:
            st.session_state["manual_page"] = 1
        page = st.session_state["manual_page"]
        visible = filtered_manuals[:page * PAGE_SIZE]
        remaining = len(filtered_manuals) - len(visible)

        domain_icons = {"BSP": "💻", "CLK": "⏰", "SWITCH": "🔌", "OTHER": "📋"}

        with st.container(border=True):
            if not filtered_manuals:
                st.caption("没有匹配的手册")
            else:
                for m in visible:
                    is_sel = m["key"] in st.session_state["sel_manual_keys"]
                    icon = domain_icons.get(m["domain"], "📋")
                    col_ck, col_info = st.columns([1, 11])
                    with col_ck:
                        new_val = st.checkbox(
                            m["file"], value=is_sel, key=f"mck_{m['key']}",
                            label_visibility="collapsed",
                        )
                    with col_info:
                        color = "#60A5FA" if new_val else "#6B7280"
                        st.markdown(f"""
                        <div style="display:flex; align-items:center; gap:8px; margin-top:-4px;">
                            <span style="font-size:0.82rem; color:{color};">{icon} {m['file']}</span>
                            <span class="file-domain">{m['domain']}</span>
                        </div>
                        """, unsafe_allow_html=True)

                    # 同步 session_state
                    if new_val and m["key"] not in st.session_state["sel_manual_keys"]:
                        st.session_state["sel_manual_keys"].add(m["key"])
                    elif not new_val and m["key"] in st.session_state["sel_manual_keys"]:
                        st.session_state["sel_manual_keys"].discard(m["key"])

                if remaining > 0:
                    if st.button(f"📥 加载更多 (还有 {remaining} 个)", key="m_load_more",
                                 use_container_width=True):
                        st.session_state["manual_page"] += 1
                        st.rerun()

    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)

    # ============================================================
    # Step 2: 选择日志文件
    # ============================================================
    st.markdown(f"""
    <div class="step-header">
        <div class="step-num {'active' if total_logs > 0 else 'inactive'}">2</div>
        <div class="step-label">选择日志文件</div>
        <div class="step-count">{len(st.session_state['sel_log_keys'])} / {total_logs} 已选</div>
    </div>
    """, unsafe_allow_html=True)

    if total_logs == 0:
        st.info("👈 请在左侧「📂 日志源」上传日志")
    else:
        # 搜索 + 操作栏
        lc1, lc2, lc3 = st.columns([5, 1, 1])
        with lc1:
            log_search = st.text_input(
                "搜索日志", key="l_search_input",
                placeholder=f"🔍 在 {total_logs} 个日志中搜索...",
                label_visibility="collapsed",
            )
        with lc2:
            if st.button("全选", key="l_select_all", use_container_width=True):
                st.session_state["sel_log_keys"] = set(log_files)
                st.rerun()
        with lc3:
            if st.button("清空", key="l_clear_all", use_container_width=True):
                st.session_state["sel_log_keys"] = set()
                st.rerun()

        # 过滤
        filtered_logs = log_files
        if log_search.strip():
            q = log_search.strip().lower()
            filtered_logs = [f for f in filtered_logs if q in f.lower()]

        # 通配符批量选
        with st.popover("⚡ 批量选择"):
            l_pattern = st.text_input("通配符模式", placeholder="*2026-02-06*  或  *.log",
                                      key="l_batch_pattern", help="支持 * 和 ? 通配符")
            if l_pattern.strip():
                l_matched = [f for f in log_files
                             if fnmatch.fnmatch(f.lower(), l_pattern.strip().lower())]
                st.caption(f"匹配 **{len(l_matched)}** / {total_logs} 个日志")
                lbc1, lbc2 = st.columns(2)
                if lbc1.button("选中匹配项", key="l_batch_add", use_container_width=True):
                    for f in l_matched:
                        st.session_state["sel_log_keys"].add(f)
                    st.rerun()
                if lbc2.button("取消匹配项", key="l_batch_remove", use_container_width=True):
                    for f in l_matched:
                        st.session_state["sel_log_keys"].discard(f)
                    st.rerun()

        # 分页显示
        if "log_page" not in st.session_state:
            st.session_state["log_page"] = 1
        l_page = st.session_state["log_page"]
        l_visible = filtered_logs[:l_page * PAGE_SIZE]
        l_remaining = len(filtered_logs) - len(l_visible)

        with st.container(border=True):
            if not filtered_logs:
                st.caption("没有匹配的日志")
            else:
                for f in l_visible:
                    is_sel = f in st.session_state["sel_log_keys"]
                    size_str = _get_file_size_str(os.path.join(user_log_dir, f)) if user_log_dir else ""
                    col_ck, col_info = st.columns([1, 11])
                    with col_ck:
                        new_val = st.checkbox(f, value=is_sel, key=f"lck_{f}", label_visibility="collapsed")
                    with col_info:
                        color = "#60A5FA" if new_val else "#6B7280"
                        st.markdown(f"""
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:-4px;">
                            <span style="font-size:0.82rem; color:{color};">📄 {f}</span>
                            <span style="font-size:0.72rem; color:#4B5563;">{size_str}</span>
                        </div>
                        """, unsafe_allow_html=True)

                    if new_val and f not in st.session_state["sel_log_keys"]:
                        st.session_state["sel_log_keys"].add(f)
                    elif not new_val and f in st.session_state["sel_log_keys"]:
                        st.session_state["sel_log_keys"].discard(f)

                if l_remaining > 0:
                    if st.button(f"📥 加载更多 (还有 {l_remaining} 个)", key="l_load_more",
                                 use_container_width=True):
                        st.session_state["log_page"] += 1
                        st.rerun()

    # ============================================================
    # 已选摘要面板 + 任务预估
    # ============================================================
    sel_mans = []
    for key in st.session_state.get("sel_manual_keys", set()):
        parts = key.split("||", 1)
        if len(parts) == 2:
            sel_mans.append({"domain": parts[0], "file": parts[1]})

    sel_logs = [f for f in log_files if f in st.session_state.get("sel_log_keys", set())]

    task_count = len(sel_mans) * len(sel_logs)

    # 摘要面板
    if sel_mans or sel_logs:
        domain_counts = {}
        for m in sel_mans:
            domain_counts[m["domain"]] = domain_counts.get(m["domain"], 0) + 1
        man_tags = "".join([f'<span class="sel-tag">{d}: {c}</span>' for d, c in domain_counts.items()])

        st.markdown(f"""
        <div class="sel-summary">
            <div class="sel-summary-row">
                <div>
                    <span style="font-size:0.82rem; color:#9CA3AF;">📚 手册</span>
                    <strong style="color:#60A5FA; margin:0 4px;">{len(sel_mans)}</strong>
                    {man_tags}
                    <span style="margin:0 8px; color:#374151;">|</span>
                    <span style="font-size:0.82rem; color:#9CA3AF;">📄 日志</span>
                    <strong style="color:#60A5FA; margin:0 4px;">{len(sel_logs)}</strong>
                </div>
                <div>
                    <span style="font-size:0.92rem; font-weight:700; color:#F9FAFB;">
                        共 <span style="color:#4F8BF9;">{task_count}</span> 个分析任务
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 启动按钮
    st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)

    if task_count == 0:
        btn_text = "🚀 请选择手册和日志后启动分析"
    else:
        btn_text = f"🚀 启动分析  —  {len(sel_logs)} 日志 × {len(sel_mans)} 手册 = {task_count} 个任务"

    btn = st.button(btn_text, type="primary", use_container_width=True, disabled=(task_count == 0))

    return sel_mans, sel_logs, btn


# =========================================================================
# 3. 结果卡片
# =========================================================================
def render_result_card(box, info, res, trace_data=None):
    """渲染结果卡片"""
    dom, file = info["domain"], info["file"]
    domain_icons = {"BSP": "💻", "CLK": "⏰", "SWITCH": "🔌", "OTHER": "📋"}
    icon = domain_icons.get(dom, "📋")

    is_fault = res.get("is_fault", False)
    confidence = res.get("confidence", 0)
    title = res.get("title", "未知")
    reason = res.get("reason", "")
    fix = res.get("fix", "")

    conf_class = "conf-high" if confidence >= 75 else "conf-mid" if confidence >= 40 else "conf-low"
    card_class = "fault" if is_fault else "ok" if title != "调用异常" else "error"
    status_icon = "🔴" if is_fault else "🟢" if title != "调用异常" else "⚠️"
    status_text = "故障确认" if is_fault else "正常" if title not in ("调用异常", "Pipeline Error") else "异常"

    box.markdown(f"""
    <div class="result-card {card_class}">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div class="result-title">{status_icon} {icon} [{dom}] {file}</div>
            <span class="status-badge badge-{'amber' if is_fault else 'green' if title != '调用异常' else 'gray'}">{status_text}</span>
        </div>
        {'<div style="font-size:0.95rem; font-weight:600; color:#F87171; margin:6px 0;">📋 ' + title + '</div>' if is_fault else ''}
        <div style="display:flex; align-items:center; gap:8px; margin-top:6px;">
            <span style="font-size:0.78rem; color:#9CA3AF;">置信度</span>
            <div class="conf-bar-bg" style="flex:1;">
                <div class="conf-bar-fill {conf_class}" style="width:{confidence}%;"></div>
            </div>
            <span style="font-size:0.85rem; font-weight:700; color:{'#F87171' if confidence >= 75 else '#FBBF24' if confidence >= 40 else '#9CA3AF'};">{confidence}%</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if is_fault:
        with st.expander("📋 详细报告", expanded=True):
            col_r, col_f = st.columns(2)
            with col_r:
                st.markdown("**🔍 根因分析**")
                st.info(reason if reason else "无详细说明")
            with col_f:
                st.markdown("**🔧 修复建议**")
                st.success(fix if fix else "无建议")
    elif title in ("调用异常", "Pipeline Error"):
        st.warning(f"⚠️ {reason}")

    if trace_data:
        with st.expander("🧠 AI 思考过程", expanded=False):
            steps = trace_data.get("steps", [])
            if steps:
                st.markdown("**Pipeline 执行轨迹**")
                for s in steps:
                    st.markdown(f"""
                    <div class="step-item"><div class="step-text">{s}</div></div>
                    """, unsafe_allow_html=True)

            tab_names, tab_contents = [], []
            if trace_data.get("log_summary"):
                tab_names.append("🕵️ Log Agent")
                tab_contents.append(("json", trace_data["log_summary"]))
            if trace_data.get("code_insight"):
                tab_names.append("💻 Code Agent")
                tab_contents.append(("markdown", trace_data["code_insight"]))
            if trace_data.get("raw_response"):
                tab_names.append("🧠 Boss Agent")
                tab_contents.append(("json", trace_data["raw_response"]))
            if tab_names:
                tabs = st.tabs(tab_names)
                for tab, (lang, content) in zip(tabs, tab_contents):
                    with tab:
                        st.code(content[:2000], language=lang)

            full_input = trace_data.get("final_input") or ""
            if full_input:
                st.markdown(f"""
                <div style="margin-top:12px; padding:8px 12px; background:#1A1F2E; border-radius:8px;
                            font-size:0.75rem; color:#6B7280;">
                    📏 Boss Agent 输入上下文: <strong>{len(full_input):,}</strong> 字符
                </div>
                """, unsafe_allow_html=True)
                with st.popover("📖 查看完整上下文"):
                    st.code(full_input, language="markdown")


# =========================================================================
# 4. 顶部指标
# =========================================================================
def render_metrics_header(user_id, model_name, enable_filter, enable_code_agent):
    codebase = utils.load_codebase_root()
    badges = [f'<span class="status-badge badge-blue">👤 {user_id}</span>',
              f'<span class="status-badge badge-purple">🤖 {model_name}</span>']
    if enable_filter:
        badges.append('<span class="status-badge badge-green">🔍 初筛 ON</span>')
    if enable_code_agent and codebase:
        badges.append('<span class="status-badge badge-green">💻 代码审计 ON</span>')
    elif not codebase:
        badges.append('<span class="status-badge badge-gray">💻 代码库未挂载</span>')
    st.markdown("".join(badges), unsafe_allow_html=True)


def render_scan_dashboard(results: list):
    total = len(results)
    faults = sum(1 for r in results if r.get("is_fault"))
    ok = total - faults
    avg_conf = sum(r.get("confidence", 0) for r in results) / total if total > 0 else 0
    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-value">{total}</div>
            <div class="metric-label">总分析数</div>
        </div>
        <div class="metric-card">
            <div class="metric-value {'fault' if faults > 0 else 'ok'}">{faults}</div>
            <div class="metric-label">🔴 发现故障</div>
        </div>
        <div class="metric-card">
            <div class="metric-value ok">{ok}</div>
            <div class="metric-label">🟢 正常</div>
        </div>
        <div class="metric-card">
            <div class="metric-value {'warn' if avg_conf >= 60 else 'ok'}">{avg_conf:.0f}%</div>
            <div class="metric-label">平均置信度</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
