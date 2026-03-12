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
    "DeepSeek": ("https://api.deepseek.com", "deepseek-chat"),
    "OpenAI": ("https://api.openai.com/v1", "gpt-4o"),
    "通义千问": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-max"),
    "自定义": ("", ""),
}

# ── LLM 调用（不依赖 config.py，直接接收 client）────────────────────────────

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
st.title("📄 简历定制工具")
st.caption("上传简历 + 粘贴 JD，自动生成针对性修改建议，确认后下载定制版 Word 简历")

# ── 侧边栏：API 配置 ──────────────────────────────────────────────────────────

with st.sidebar:
    st.header("API 配置")
    provider = st.selectbox("服务商", list(PRESET_APIS.keys()))
    default_base_url, default_model = PRESET_APIS[provider]

    api_key = st.text_input("API Key", type="password", placeholder="sk-...")
    base_url = st.text_input("Base URL", value=default_base_url)
    model_name = st.text_input("模型", value=default_model)

    st.divider()
    st.caption("API Key 仅在本次会话内存中使用，不会被存储或上传。")

# ── 第一步：上传简历 + 填写 JD ───────────────────────────────────────────────

st.subheader("第一步：上传简历和岗位描述")
col1, col2 = st.columns(2)

with col1:
    uploaded_file = st.file_uploader("基础简历（.docx）", type=["docx"])
    job_name = st.text_input("岗位名称", placeholder="如：AI产品经理、数据分析师")

with col2:
    jd_text = st.text_area("岗位描述（JD）", height=280, placeholder="将招聘 JD 粘贴到这里...")

# ── 分析按钮 ──────────────────────────────────────────────────────────────────

api_ready = bool(api_key.strip() and base_url.strip() and model_name.strip())
inputs_ready = bool(uploaded_file and jd_text.strip())

if not api_ready:
    st.info("请在左侧填写 API 配置。")

if st.button(
    "🔍 分析并生成修改建议",
    disabled=not (api_ready and inputs_ready),
    type="primary",
):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "resume.docx"
        tmp_path.write_bytes(uploaded_file.getvalue())

        with st.spinner("正在读取简历并调用 LLM 分析 JD..."):
            try:
                client = OpenAI(api_key=api_key, base_url=base_url)
                resume_paras = get_resume_content(tmp_path)
                modifications = _call_llm(client, model_name, jd_text, resume_paras)

                st.session_state.update(
                    resume_paras=resume_paras,
                    modifications=modifications,
                    resume_bytes=uploaded_file.getvalue(),
                    jd_text=jd_text,
                    job_name=job_name.strip() or "定制版",
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name,
                    output_bytes=None,
                )
            except Exception as e:
                st.error(f"分析失败：{e}")

# ── 第二步：审阅修改建议 ───────────────────────────────────────────────────────

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

# ── 第三步：下载 ──────────────────────────────────────────────────────────────

if st.session_state.get("output_bytes"):
    st.divider()
    st.subheader("第三步：下载简历")
    st.success("定制版简历已生成！")

    file_name = f"简历_{st.session_state.job_name}版.docx"
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
