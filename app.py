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

from resume_tailor.src.resume_tailor import (
    _GREETING_SYSTEM_PROMPT,
    _SYSTEM_PROMPT,
    _build_resume_str,
    _parse_llm_json,
    apply_modifications,
    get_resume_content,
)

# ── API 服务商预设 ────────────────────────────────────────────────────────────

PRESET_APIS = {
    "DeepSeek":  ("https://api.deepseek.com",                           "deepseek-chat"),
    "通义千问":   ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-max"),
    "Kimi":      ("https://api.moonshot.cn/v1",                         "moonshot-v1-8k"),
    "MiniMax":   ("https://api.minimax.chat/v1",                        "MiniMax-Text-01"),
    "火山引擎":   ("https://ark.cn-beijing.volces.com/api/v3",           ""),  # 模型名因 endpoint 而异
    "OpenAI":    ("https://api.openai.com/v1",                          "gpt-4o"),
    "自定义":    ("", ""),
}

# ── LLM 调用 ──────────────────────────────────────────────────────────────────


def _call_llm(client: OpenAI, model: str, jd: str, resume_paras: list) -> list:
    user_msg = f"【岗位描述】\n{jd}\n\n【当前简历段落】\n{_build_resume_str(resume_paras)}"
    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    return _parse_llm_json(response.choices[0].message.content)


def _call_llm_with_feedback(
    client: OpenAI,
    model: str,
    jd: str,
    resume_paras: list,
    prev_modifications: list,
    feedback: str,
) -> list:
    orig_map = {p["index"]: p["text"] for p in resume_paras}
    prev_lines = [
        f"  段落 {m['para_index']}: {orig_map.get(m['para_index'], '')!r} → "
        f"{''.join(s['text'] for s in m.get('segments', []))!r}  ({m.get('reason', '')})"
        for m in prev_modifications
    ]
    user_msg = (
        f"【岗位描述】\n{jd}\n\n"
        f"【当前简历段落】\n{_build_resume_str(resume_paras)}\n\n"
        f"【上一版修改建议】\n" + "\n".join(prev_lines) + "\n\n"
        f"【用户反馈】\n{feedback}\n\n"
        "请根据用户反馈调整修改建议，重新输出完整 JSON 数组。"
    )
    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    return _parse_llm_json(response.choices[0].message.content)


def _generate_greeting(client: OpenAI, model: str, jd: str, resume_paras: list) -> str:
    user_msg = f"【岗位描述】\n{jd}\n\n【简历内容】\n{_build_resume_str(resume_paras)}"
    response = client.chat.completions.create(
        model=model,
        max_tokens=300,
        messages=[
            {"role": "system", "content": _GREETING_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    return response.choices[0].message.content.strip()


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
            help=(
                "请上传 Word .docx 格式（不支持 .doc / .pdf / .wps）。\n\n"
                "**兼容性说明**\n"
                "- 纯文字段落排版：完整支持，内容可自动修改\n"
                "- 表格布局排版：支持读取（LLM 可看到内容），但表格内文字暂不支持自动改写\n"
                "- 文本框、艺术字：无法读取\n\n"
                "如遇兼容问题，建议将简历另存为「纯段落」格式后重新上传。"
            ),
        )
        job_name = st.text_input("岗位名称", placeholder="如：AI产品经理、数据分析师")

    with col2:
        jd_text = st.text_area("岗位描述（JD）", height=280, placeholder="将招聘 JD 粘贴到这里...")

    # ── 分析按钮 ──────────────────────────────────────────────────────────────

    api_ready    = bool(api_key.strip() and base_url.strip() and model_name.strip())
    inputs_ready = bool(uploaded_file and jd_text.strip())

    if not api_ready:
        st.info("请在左侧填写 API 配置（或在「⚙️ 设置」中保存配置）。")

    if st.button(
        "🔍 分析并生成修改建议",
        disabled=not (api_ready and inputs_ready),
        type="primary",
    ):
        resume_bytes = uploaded_file.getvalue()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "resume.docx"
            tmp_path.write_bytes(resume_bytes)

            with st.spinner("正在读取简历并调用 LLM 分析 JD..."):
                try:
                    client = OpenAI(api_key=api_key, base_url=base_url)
                    resume_paras = get_resume_content(tmp_path)
                    modifications = _call_llm(client, model_name, jd_text, resume_paras)

                    # 诊断：统计表格 vs 正文段落占比
                    table_count  = sum(1 for p in resume_paras if p.get("in_table"))
                    normal_count = sum(1 for p in resume_paras if not p.get("in_table"))
                    if normal_count == 0:
                        st.warning(
                            "⚠️ 未检测到可修改的正文段落，简历可能全部采用表格排版。"
                            "LLM 可以读取内容，但自动改写功能受限，建议将简历改为段落格式后重试。"
                        )
                    elif table_count > normal_count:
                        st.info(
                            f"ℹ️ 检测到简历以表格为主（{table_count} 行表格、{normal_count} 个正文段落）。"
                            "表格内文字已提供给 LLM 参考，但自动改写仅作用于正文段落部分。"
                        )

                    st.session_state.update(
                        resume_paras=resume_paras,
                        modifications=modifications,
                        resume_bytes=resume_bytes,
                        jd_text=jd_text,
                        job_name=job_name.strip() or "定制版",
                        api_key=api_key,
                        base_url=base_url,
                        model_name=model_name,
                        output_bytes=None,
                    )
                except Exception as e:
                    st.error(f"分析失败：{e}")

    # ── 第二步：审阅修改建议 ───────────────────────────────────────────────────

    if st.session_state.get("modifications"):
        st.divider()
        st.subheader("第二步：审阅修改建议")

        mods = st.session_state.modifications
        paras = st.session_state.resume_paras
        orig_map = {p["index"]: p["text"] for p in paras}

        for i, m in enumerate(mods, 1):
            orig = orig_map.get(m["para_index"], "（未找到）")
            new_text = "".join(s["text"] for s in m.get("segments", []))
            with st.expander(
                f"[{i}] 段落 {m['para_index']} — {m.get('reason', '')}",
                expanded=True,
            ):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**原文**")
                    st.text(orig)
                with c2:
                    st.markdown("**修改后**")
                    st.text(new_text)

        # 反馈 + 重新生成
        feedback = st.text_input(
            "有修改意见？输入后点击「重新生成」；无意见直接点「确认生成」。"
        )

        col_regen, col_confirm, _ = st.columns([1, 1, 2])

        with col_regen:
            if st.button("🔄 重新生成", disabled=not feedback.strip()):
                with st.spinner("正在根据您的意见重新生成..."):
                    try:
                        client = OpenAI(
                            api_key=st.session_state.api_key,
                            base_url=st.session_state.base_url,
                        )
                        new_mods = _call_llm_with_feedback(
                            client,
                            st.session_state.model_name,
                            st.session_state.jd_text,
                            st.session_state.resume_paras,
                            st.session_state.modifications,
                            feedback,
                        )
                        st.session_state.modifications = new_mods
                        st.session_state.output_bytes = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"重新生成失败：{e}")

        with col_confirm:
            if st.button("✅ 确认，生成 Word 简历", type="primary"):
                with tempfile.TemporaryDirectory() as tmpdir:
                    base_path = Path(tmpdir) / "base.docx"
                    output_path = Path(tmpdir) / f"简历_{st.session_state.job_name}版.docx"
                    base_path.write_bytes(st.session_state.resume_bytes)

                    try:
                        apply_modifications(
                            base_path, st.session_state.modifications, output_path
                        )
                        st.session_state.output_bytes = output_path.read_bytes()
                    except Exception as e:
                        st.error(f"生成失败：{e}")

    # ── 第三步：下载 ──────────────────────────────────────────────────────────

    if st.session_state.get("output_bytes"):
        st.divider()
        st.subheader("第三步：下载简历")
        st.success("定制版简历已生成！")

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

        st.divider()
        if st.button("✉️ 生成 BOSS 直聘打招呼消息"):
            with st.spinner("正在生成..."):
                try:
                    client = OpenAI(
                        api_key=st.session_state.api_key,
                        base_url=st.session_state.base_url,
                    )
                    greeting = _generate_greeting(
                        client,
                        st.session_state.model_name,
                        st.session_state.jd_text,
                        st.session_state.resume_paras,
                    )
                    st.text_area("打招呼消息（可直接复制）", value=greeting, height=150)
                except Exception as e:
                    st.error(f"生成失败：{e}")

# ════════════════════════════════════════════════════════════════════════════
# 设置标签页
# ════════════════════════════════════════════════════════════════════════════

with tab_settings:
    st.subheader("⚙️ 设置")
    st.caption("设置仅在本次会话内有效，关闭或刷新页面后需重新填写。")

    with st.expander("💡 没有 API Key？点此查看各平台免费领取教程", expanded=False):
        st.markdown(
            "| 平台 | 支持模型 | 获取地址 |\n"
            "|------|---------|------|\n"
            "| **字节火山引擎** | 豆包、DeepSeek、Kimi 等 | [console.volcengine.com/ark](https://console.volcengine.com/ark) |\n"
            "| **阿里云百炼** | 通义千问、DeepSeek、Kimi 等 | [bailian.console.aliyun.com](https://bailian.console.aliyun.com) |\n"
            "| **DeepSeek** | DeepSeek V3 / R1 | [platform.deepseek.com](https://platform.deepseek.com) |\n"
            "| **Kimi** | Kimi K2 系列 | [platform.moonshot.cn](https://platform.moonshot.cn) |\n"
            "| **MiniMax** | MiniMax M2 系列 | [platform.minimaxi.com](https://platform.minimaxi.com) |\n"
            "\n"
            "**通用步骤（以 DeepSeek 为例）：**\n"
            "1. 打开上方链接 → 注册账号（手机号即可）\n"
            "2. 登录后进入「API Keys」→「创建 API Key」\n"
            "3. 复制生成的 key（`sk-` 开头），粘贴到下方「API Key」输入框\n"
            "4. 在「服务商」下拉框选择对应平台，Base URL 和模型名称会自动填入\n"
        )

    with st.form("settings_form"):
        st.markdown("##### 基本信息")
        s_file_prefix = st.text_input(
            "文件名前缀（选填）",
            value=st.session_state.get("saved_file_prefix", ""),
            placeholder="如：我的简历、张三（留空亦可）",
        )
        st.caption(
            "📄 文件命名规则：\n"
            "- 未填写前缀：`产品经理_20260313_143022.docx`\n"
            "- 填写前缀「我的简历」：`我的简历_产品经理_20260313_143022.docx`\n"
            "无需填写真实姓名，自定义即可。"
        )

        st.markdown("##### API 配置")
        s_provider = st.selectbox(
            "服务商",
            list(PRESET_APIS.keys()),
            key="settings_provider",
        )
        s_def_url, s_def_model = PRESET_APIS[s_provider]

        s_api_key = st.text_input(
            "API Key",
            value=st.session_state.get("saved_api_key", ""),
            type="password",
            placeholder="sk-...",
        )
        s_base_url = st.text_input(
            "Base URL",
            value=st.session_state.get("saved_base_url", "") or s_def_url,
        )
        s_model = st.text_input(
            "模型",
            value=st.session_state.get("saved_model", "") or s_def_model,
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
