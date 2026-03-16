"""
简历定制工具 — Web 界面
运行：streamlit run app.py
"""

import sys
import tempfile
from pathlib import Path

import streamlit as st
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))

from resume_tailor.src.ats_generator import AtsGenerator
from resume_tailor.src.resume_tailor import (
    call_llm_ats,
    call_llm_ats_with_feedback,
    extract_plain_text,
    get_resume_content,
)

# ── API 服务商预设 ────────────────────────────────────────────────────────────

PRESET_APIS = {
    "Google Gemini":  ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.0-flash"),
    "DeepSeek":       ("https://api.deepseek.com",                                 "deepseek-chat"),
    "通义千问":        ("https://dashscope.aliyuncs.com/compatible-mode/v1",        "qwen-max"),
    "Kimi":           ("https://api.moonshot.cn/v1",                               "moonshot-v1-8k"),
    "MiniMax":        ("https://api.minimax.chat/v1",                              "MiniMax-Text-01"),
    "火山引擎":        ("https://ark.cn-beijing.volces.com/api/v3",                 ""),  # 模型名因 endpoint 而异
    "OpenAI":         ("https://api.openai.com/v1",                                "gpt-4o"),
    "自定义":          ("", ""),
}

# ── LLM 调用 ──────────────────────────────────────────────────────────────────


# ── 页面配置 ──────────────────────────────────────────────────────────────────

st.set_page_config(page_title="简历定制工具", page_icon="📄", layout="wide")

# ── 侧边栏：配置信息 ──────────────────────────────────────────────────────────

with st.sidebar:
    st.header("配置信息")
    _saved_key    = st.session_state.get("saved_api_key",     "")
    _saved_url    = st.session_state.get("saved_base_url",    "")
    _saved_model  = st.session_state.get("saved_model",       "")
    _saved_prefix = st.session_state.get("saved_file_prefix", "")

    if _saved_key and _saved_url and _saved_model:
        provider_label = "自定义"
        for _name, (_url, _) in PRESET_APIS.items():
            if _url and _url == _saved_url:
                provider_label = _name
                break
        st.success("✅ 配置已完成")
        st.caption(f"文件前缀：{_saved_prefix or '（未设置）'}")
        st.caption(f"服务商：{provider_label}")
        st.caption(f"Base URL：{_saved_url}")
        st.caption(f"模型：{_saved_model}")
    else:
        st.warning("尚未完成配置")

    st.caption("前往「⚙️ 设置」填写或修改配置。")
    st.divider()
    st.caption("API Key 仅在本次会话内存中使用，不会上传至服务器。")

# 从设置页保存的 session_state 读取 API 参数
api_key    = st.session_state.get("saved_api_key",  "")
base_url   = st.session_state.get("saved_base_url", "")
model_name = st.session_state.get("saved_model",    "")

# ── 主体：标签页 ──────────────────────────────────────────────────────────────

st.title("📄 简历定制工具")
st.caption("上传简历 + 粘贴 JD，自动生成针对性修改建议，确认后下载定制版 Word 简历")

tab_main, tab_settings = st.tabs(["📝 简历定制", "⚙️ 设置"])

# ════════════════════════════════════════════════════════════════════════════
# 简历定制标签页
# ════════════════════════════════════════════════════════════════════════════

with tab_main:

    # 首次使用提示
    if not st.session_state.get("saved_api_key"):
        st.info(
            "尚未完成初始设置。请前往「⚙️ 设置」标签页填写文件名前缀和 API 配置，"
            "然后点击「保存设置」。",
            icon="ℹ️",
        )

    # ── 第一步：上传简历 + 填写 JD ───────────────────────────────────────────

    st.subheader("第一步：上传简历和岗位描述")
    st.warning(
        "**使用过程中请勿随意刷新或关闭此页面。**\n\n"
        "本工具运行在云端，您填写的配置、上传的简历和分析结果均只保存在当前浏览器窗口中，"
        "一旦刷新或关闭，所有数据将立即清空，需要重新开始。",
        icon="⚠️",
    )
    col1, col2 = st.columns(2)

    with col1:
        uploaded_file = st.file_uploader(
            "基础简历（.docx）",
            type=["docx"],
            help="请上传 Word .docx 格式（不支持 .doc / .pdf / .wps）。",
        )
        job_name = st.text_input("岗位名称", placeholder="如：AI产品经理、数据分析师")

    with col2:
        jd_text = st.text_area("岗位描述（JD）", height=280, placeholder="将招聘 JD 粘贴到这里...")

    # ── 生成按钮 ──────────────────────────────────────────────────────────────

    api_ready    = bool(api_key.strip() and base_url.strip() and model_name.strip())
    inputs_ready = bool(uploaded_file and jd_text.strip())

    if not api_ready:
        st.info("请在左侧填写 API 配置（或在「⚙️ 设置」中保存配置）。")

    if st.button(
        "🚀 生成 ATS 简历",
        disabled=not (api_ready and inputs_ready),
        type="primary",
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "resume.docx"
            tmp_path.write_bytes(uploaded_file.getvalue())

            with st.spinner("正在读取简历并生成定制内容..."):
                try:
                    _client      = OpenAI(api_key=api_key, base_url=base_url)
                    resume_paras = get_resume_content(tmp_path)
                    resume_text  = extract_plain_text(resume_paras)
                    profile, changes = call_llm_ats(jd_text, resume_text, client=_client, model=model_name)

                    st.session_state.update(
                        resume_text=resume_text,
                        ats_profile=profile,
                        ats_changes=changes,
                        jd_text=jd_text,
                        job_name=job_name.strip() or "定制版",
                        api_key=api_key,
                        base_url=base_url,
                        model_name=model_name,
                        output_bytes=None,
                    )
                except Exception as e:
                    err_str = str(e)
                    if "402" in err_str or "Insufficient Balance" in err_str:
                        st.error("API 账户余额不足，请前往服务商平台充值后重试。")
                    elif "401" in err_str or "Unauthorized" in err_str or "invalid api key" in err_str.lower():
                        st.error("API Key 无效或已过期，请在「⚙️ 设置」中重新填写。")
                    elif "429" in err_str or "rate limit" in err_str.lower():
                        st.error("请求过于频繁（Rate Limit），请稍等片刻后重试。")
                    elif "404" in err_str or ("model" in err_str.lower() and "not found" in err_str.lower()):
                        st.error("模型名称不存在，请在「⚙️ 设置」中检查模型名称是否正确。")
                    else:
                        st.error(f"生成失败：{e}")

    # ── 第二步：审阅生成内容 ──────────────────────────────────────────────────

    if st.session_state.get("ats_profile"):
        st.divider()
        st.subheader("第二步：审阅修改内容")

        changes = st.session_state.get("ats_changes", [])
        if not changes:
            st.info("LLM 未返回具体修改条目，请直接确认生成或提供反馈后重新生成。")
        else:
            for i, ch in enumerate(changes, 1):
                label   = ch.get("label", f"条目 {i}")
                section = ch.get("section", "")

                section_label = {"skills": "专业技能", "work_experience": "实习经历", "projects": "项目经历"}.get(section, section)
                title = f"[{i}] {section_label} · {label}"

                with st.expander(title, expanded=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**原文**")
                        st.text(ch.get("original", ""))
                    with c2:
                        st.markdown("**修改后**")
                        st.text(ch.get("modified", ""))

        # 反馈 + 重新生成
        feedback = st.text_input(
            "有修改意见？输入后点击「重新生成」；无意见直接点「确认生成」。"
        )

        col_regen, col_confirm, _ = st.columns([1, 1, 2])

        with col_regen:
            if st.button("🔄 重新生成", disabled=not feedback.strip()):
                with st.spinner("正在根据您的意见重新生成..."):
                    try:
                        _client = OpenAI(
                            api_key=st.session_state.api_key,
                            base_url=st.session_state.base_url,
                        )
                        new_profile, new_changes = call_llm_ats_with_feedback(
                            st.session_state.jd_text,
                            st.session_state.resume_text,
                            st.session_state.ats_profile,
                            feedback,
                            client=_client,
                            model=st.session_state.model_name,
                        )
                        st.session_state.ats_profile = new_profile
                        st.session_state.ats_changes = new_changes
                        st.session_state.output_bytes = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"重新生成失败：{e}")

        with col_confirm:
            if st.button("✅ 确认，生成 Word 简历", type="primary"):
                with tempfile.TemporaryDirectory() as tmpdir:
                    output_path = Path(tmpdir) / "output.docx"
                    try:
                        AtsGenerator(st.session_state.ats_profile).generate(output_path)
                        st.session_state.output_bytes = output_path.read_bytes()
                    except Exception as e:
                        st.error(f"生成失败：{e}")

    # ── 第三步：下载 ──────────────────────────────────────────────────────────

    if st.session_state.get("output_bytes"):
        st.divider()
        st.subheader("第三步：下载简历")
        st.success("ATS 简历已生成！")

        from datetime import datetime as _dt
        _prefix    = st.session_state.get("saved_file_prefix", "").strip()
        _timestamp = _dt.now().strftime("%Y%m%d_%H%M%S")
        _job       = st.session_state.job_name
        file_name  = f"{_prefix}_{_job}_{_timestamp}.docx" if _prefix else f"{_job}_{_timestamp}.docx"
        st.download_button(
            label="⬇️ 下载 Word 简历（.docx）",
            data=st.session_state.output_bytes,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
        )
        st.caption("下载后在 Word 中打开，手动导出 PDF。")


# ════════════════════════════════════════════════════════════════════════════
# 设置标签页
# ════════════════════════════════════════════════════════════════════════════

with tab_settings:
    st.subheader("⚙️ 设置")
    st.caption("设置仅在本次会话内有效，关闭或刷新页面后需重新填写。")

    with st.expander("💡 支持的服务商及 API Key 获取方式", expanded=False):
        st.markdown(
            "| 平台 | 支持模型 | 获取地址 |\n"
            "|------|---------|------|\n"
            "| **Google Gemini** | Gemini 2.0 Flash 等 | [aistudio.google.com](https://aistudio.google.com) |\n"
            "| **字节火山引擎** | 豆包、DeepSeek、Kimi 等 | [console.volcengine.com/ark](https://console.volcengine.com/ark) |\n"
            "| **阿里云百炼** | 通义千问、DeepSeek、Kimi 等 | [bailian.console.aliyun.com](https://bailian.console.aliyun.com) |\n"
            "| **DeepSeek** | DeepSeek V3 / R1 | [platform.deepseek.com](https://platform.deepseek.com) |\n"
            "| **Kimi** | Kimi K2 系列 | [platform.moonshot.cn](https://platform.moonshot.cn) |\n"
            "| **MiniMax** | MiniMax M2 系列 | [platform.minimaxi.com](https://platform.minimaxi.com) |\n"
            "| **OpenAI** | GPT-4o 等 | [platform.openai.com](https://platform.openai.com) |\n"
            "\n"
            "**通用步骤：** 注册 → 进入「API Keys」→ 创建并复制 key → 粘贴到下方输入框，选择对应服务商。\n"
        )

    st.markdown("##### 基本信息")
    s_file_prefix = st.text_input(
        "文件名前缀（选填）",
        value=st.session_state.get("saved_file_prefix", ""),
        placeholder="如：我的简历、张三（留空亦可）",
        key="s_file_prefix_input",
    )
    st.caption(
        "📄 文件命名规则（其中「岗位名称」取自简历定制页第一步填写的岗位名称）：\n"
        "- 未填写前缀：`岗位名称_20260313_143022.docx`\n"
        "- 填写前缀「我的简历」：`我的简历_岗位名称_20260313_143022.docx`\n"
        "无需填写真实姓名，自定义即可。"
    )

    st.markdown("##### API 配置")
    s_provider = st.selectbox(
        "服务商",
        list(PRESET_APIS.keys()),
        key="settings_provider",
    )
    s_def_url, s_def_model = PRESET_APIS[s_provider]

    with st.form("settings_form"):
        s_api_key = st.text_input(
            "API Key",
            value=st.session_state.get("saved_api_key", ""),
            type="password",
            placeholder="sk-...",
        )
        s_base_url = st.text_input(
            "Base URL",
            value=s_def_url or st.session_state.get("saved_base_url", ""),
        )
        s_model = st.text_input(
            "模型",
            value=s_def_model or st.session_state.get("saved_model", ""),
        )

        submitted = st.form_submit_button("💾 保存设置", type="primary")

    if submitted:
        errors = []
        if not s_api_key.strip():
            errors.append("API Key 不能为空")
        if not s_base_url.strip():
            errors.append("Base URL 不能为空")
        if not s_model.strip():
            errors.append("模型名称不能为空")

        if errors:
            for e in errors:
                st.error(e)
        else:
            st.session_state.saved_file_prefix = s_file_prefix.strip()
            st.session_state.saved_api_key     = s_api_key.strip()
            st.session_state.saved_base_url    = s_base_url.strip()
            st.session_state.saved_model       = s_model.strip()

            st.success("设置已保存 ✓ 侧边栏配置信息将在下次操作时自动更新。")
            st.rerun()
