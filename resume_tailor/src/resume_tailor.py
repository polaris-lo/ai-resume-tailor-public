"""
简历定制核心模块

根据岗位 JD，调用 LLM（OpenAI 兼容格式）生成针对性修改建议，输出定制版 .docx。

格式规范（自动强制执行）：
- 全文宋体五号（10.5pt），含 ascii/hAnsi/eastAsia/cs 四个字符集
- 加粗规则：只加粗关键词（技能类别名、条目类型词、关键数字），不整句加粗
- 无空段落，无嵌入 sectPr
"""

from __future__ import annotations

import json
import shutil
from json_repair import repair_json
import sys
from pathlib import Path

from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from openai import OpenAI

# 将项目根目录加入 sys.path，以便 import config
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import load_config

OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"


def _get_client():
    cfg = load_config()
    return OpenAI(
        api_key=cfg["llm"]["api_key"],
        base_url=cfg["llm"]["base_url"],
    ), cfg["llm"]["model"]


def _get_user_name() -> str:
    return load_config()["user_name"]


def _get_base_resume() -> Path:
    cfg = load_config()
    p = Path(cfg["resume_path"]).expanduser()
    return p


# ──────────────────────────────────────────────────────────────
# 读取简历内容
# ──────────────────────────────────────────────────────────────

def get_resume_content(doc_path: Path) -> list[dict]:
    """提取简历段落结构，同时兼容表格布局。

    返回两类条目：
    - in_table=False：正文段落，有 index，可被 LLM 修改
    - in_table=True ：表格单元格文字，index=-1，仅供 LLM 阅读，不可修改
    """
    doc = Document(str(doc_path))
    result = []

    for i, para in enumerate(doc.paragraphs):
        if not para.text.strip():
            continue
        result.append({
            "index": i,
            "is_header": para.style.name == "Normal",
            "text": para.text,
            "in_table": False,
        })

    # 提取表格内容（合并相邻重复单元格，避免 python-docx 的合并单元格重复读取）
    seen = set()
    for table in doc.tables:
        for row in table.rows:
            row_texts = []
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text and cell_text not in seen:
                    seen.add(cell_text)
                    row_texts.append(cell_text)
            if row_texts:
                result.append({
                    "index": -1,
                    "is_header": False,
                    "text": " | ".join(row_texts),
                    "in_table": True,
                })

    return result


# ──────────────────────────────────────────────────────────────
# 调用 LLM
# ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位专业的简历顾问，擅长根据岗位要求对简历进行针对性修改。

【格式规范（必须严格遵守）】
1. 只修改"专业技能"和"实习经历"中的描述句，不修改基本信息、教育背景、节标题、公司/时间行
2. 每个修改段落用 segments 表示，segments 是文本片段数组，每片段有 text 和 bold 两个字段
3. bold=true 仅用于：技能类别名、条目类型词、关键数字/比例，绝不整句加粗
4. 修改要简洁量化，突出与 JD 匹配的能力，风格与原简历一致

【特别注意】
- 简历中标注「表格内容」的部分仅供参考，不得出现在返回 JSON 中
- JSON 中只能使用「正文段落」区域里列出的 index 编号

【返回格式】
只返回一个 JSON 数组，不要任何其他文字：
[
  {
    "para_index": <段落在原文中的 index 编号>,
    "reason": "<一句话说明修改原因>",
    "segments": [
      {"text": "关键词", "bold": true},
      {"text": "：描述文字", "bold": false}
    ]
  }
]
"""


def _parse_llm_json(raw: str) -> list[dict]:
    """解析 LLM 返回的 JSON，兼容 ```json ... ``` 包裹及常见格式错误。"""
    raw = raw.strip()
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("["):
                raw = part
                break
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(repair_json(raw))


def _build_resume_str(resume_paras: list[dict]) -> str:
    normal_lines = []
    table_lines = []
    for p in resume_paras:
        if p.get("in_table"):
            table_lines.append(f"  {p['text']}")
        else:
            tag = "[节标题]" if p["is_header"] else "       "
            normal_lines.append(f"  {p['index']:2d}. {tag} {p['text']}")

    parts = ["【正文段落（可修改，使用上方 index 编号）】"] + normal_lines
    if table_lines:
        parts += ["", "【表格内容（仅供参考，不可修改，不得出现在 JSON 中）】"] + table_lines
    return "\n".join(parts)


def call_llm(jd: str, resume_paras: list[dict]) -> list[dict]:
    """调用 LLM，返回段落修改列表。"""
    client, model = _get_client()
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


def call_llm_with_feedback(
    jd: str,
    resume_paras: list[dict],
    prev_modifications: list[dict],
    feedback: str,
) -> list[dict]:
    """基于用户反馈，重新调用 LLM 生成修改建议。"""
    client, model = _get_client()
    orig_map = {p["index"]: p["text"] for p in resume_paras}
    prev_lines = []
    for m in prev_modifications:
        orig = orig_map.get(m["para_index"], "")
        new_text = "".join(s["text"] for s in m.get("segments", []))
        prev_lines.append(
            f"  段落 {m['para_index']}: {orig!r} → {new_text!r}  ({m.get('reason', '')})"
        )
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


def suggest_job_name(jd: str) -> str:
    """根据 JD 内容自动推断岗位名称（不超过10个汉字）。"""
    client, model = _get_client()
    response = client.chat.completions.create(
        model=model,
        max_tokens=20,
        messages=[{
            "role": "user",
            "content": (
                "根据以下岗位描述，给出一个简短的岗位名称（不超过10个汉字，"
                "如「AI产品经理」、「数据分析师」），只返回名称本身，不要任何其他文字：\n\n"
                + jd[:800]
            ),
        }],
    )
    return response.choices[0].message.content.strip()


def format_modifications(modifications: list[dict], resume_paras: list[dict]) -> str:
    """格式化修改建议，便于展示给用户确认。"""
    orig_map = {p["index"]: p["text"] for p in resume_paras}
    lines = [f"共 {len(modifications)} 处修改建议：\n"]
    for i, m in enumerate(modifications, 1):
        orig = orig_map.get(m["para_index"], "（原文未找到）")
        new_text = "".join(s["text"] for s in m.get("segments", []))
        lines.append(f"[{i}] 段落 {m['para_index']} — {m.get('reason', '')}")
        lines.append(f"    原文：{orig}")
        lines.append(f"    修改：{new_text}")
        lines.append("")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# 应用修改
# ──────────────────────────────────────────────────────────────

def _set_runs(para, segments: list[dict]) -> None:
    """替换段落所有 run，统一应用宋体五号 + bold 规则。"""
    p = para._p
    for r in list(p.findall(qn("w:r"))):
        p.remove(r)
    for seg in segments:
        run = para.add_run(seg["text"])
        run.bold = seg["bold"]
        run.font.size = Pt(10.5)
        rPr = run._r.get_or_add_rPr()
        rFonts = rPr.get_or_add_rFonts()
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            rFonts.set(qn(attr), "宋体")


def apply_modifications(base_path: Path, modifications: list[dict], output_path: Path) -> None:
    """将修改应用到 docx 副本，同时清理空段落和嵌入 sectPr。"""
    shutil.copy(str(base_path), str(output_path))
    doc = Document(str(output_path))

    # 应用段落替换
    mod_map = {m["para_index"]: m for m in modifications}
    for i, para in enumerate(doc.paragraphs):
        if i in mod_map:
            _set_runs(para, mod_map[i]["segments"])

    # 清理空段落
    body = doc.element.body
    for p in list(body.findall(qn("w:p"))):
        texts = [t.text or "" for t in p.findall(".//" + qn("w:t"))]
        if not "".join(texts).strip():
            body.remove(p)

    # 清理嵌入 sectPr（连续分节符）
    for para in doc.paragraphs:
        pPr = para._p.find(qn("w:pPr"))
        if pPr is not None:
            sectPr = pPr.find(qn("w:sectPr"))
            if sectPr is not None:
                pPr.remove(sectPr)

    # 统一全文字体为宋体五号
    for para in doc.paragraphs:
        for run in para.runs:
            run.font.size = Pt(10.5)
            rPr = run._r.get_or_add_rPr()
            rFonts = rPr.get_or_add_rFonts()
            for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                rFonts.set(qn(attr), "宋体")

    doc.save(str(output_path))


# ──────────────────────────────────────────────────────────────
# ATS 流程：纯文本提取 + 结构化 profile LLM
# ──────────────────────────────────────────────────────────────

def extract_plain_text(resume_paras: list[dict]) -> str:
    """将简历段落列表合并为纯文本，去除空行。"""
    return "\n".join(p["text"] for p in resume_paras if p["text"].strip())


_ATS_SYSTEM_PROMPT = """\
你是一位资深简历优化专家。用户会提供目标岗位 JD 和简历纯文本。

你的任务：
1. 解析简历，提取结构化信息
2. 对「专业技能」「实习经历」「项目经历」的描述进行针对性改写后，直接写入输出的 JSON
3. 只返回如下结构的 JSON 对象，不要任何其他文字：

{
  "basic_info": {
    "name": "姓名",
    "phone": "手机号",
    "email": "邮箱",
    "other": ["其他基本信息，每条一个字符串"]
  },
  "education": [
    {
      "school": "学校名称",
      "degree": "学位",
      "major": "专业",
      "college": "学院（可为空字符串）",
      "start_date": "YYYY.MM",
      "end_date": "YYYY.MM 或 至今",
      "extras": ["附加信息，如 GPA、专业排名"]
    }
  ],
  "skills": { "技能类别": "改写后的技能描述" },
  "work_experience": [
    {
      "company": "公司名称",
      "title": "职位名称",
      "city": "城市（可为空字符串）",
      "start_date": "YYYY.MM",
      "end_date": "YYYY.MM 或 至今",
      "bullets": ["改写后的工作成果，每条一个字符串"]
    }
  ],
  "projects": [
    {
      "name": "项目名称",
      "role": "担任角色（可为空字符串）",
      "start_date": "YYYY.MM（可为空字符串）",
      "end_date": "YYYY.MM（可为空字符串）",
      "bullets": ["改写后的项目成果，每条一个字符串"]
    }
  ],
  "awards": [
    {"date": "YYYY.MM（可为空字符串）", "name": "奖项或证书名称"}
  ]
}

【改写规则——必须遵守】
1. 改写 = 在原文基础上替换/嵌入 JD 关键词，不是用 JD 句子替换原文
2. 原文的主语、动词、核心事实必须保留，只改措辞
3. 关键词应自然融入句子内部，而非全部堆砌在句尾
4. 只改写与 JD 直接相关的条目，无关的原样保留
5. 不得编造简历中未提及的经历或数据；严禁在句末追加原文没有的行动、成果或功能描述——即使这些词来自 JD，原文中没有做过的事就是没有做过
6. 保持各条目篇幅与原简历相近；若改写后明显长于原文，说明引入了编造内容，应删除多余部分
7. 如果简历中某条 bullet 明显是上一条的续句（如以"等""防""或"开头，或不是完整句子），将其与上一条合并为一条完整的 bullet
8. 保留每条 bullet 原有的标签前缀（如「研究设计：」「数据分析：」「AI应用能力：」），不得删除或替换

【示例】

JD 关键词：降本增效

原文："流程优化：梳理线下审批流程，推动关键环节线上化"

✗ 错误（照抄 JD）："降本增效：通过资源整合与流程再造，大幅压缩运营成本"
✗ 错误（堆砌句尾）："流程优化：梳理线下审批流程，推动关键环节线上化，支持降本增效"
✓ 正确："流程优化：梳理线下审批流程，推动关键环节线上化以压缩人工成本"
"""


def _parse_ats_json(raw: str) -> dict:
    """解析 LLM 返回的 profile JSON。"""
    raw = raw.strip()
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"):
                raw = part
                break
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        from json_repair import repair_json
        return json.loads(repair_json(raw))


def compute_changes(profile: dict, resume_text: str) -> list[dict]:
    """对比 profile 与原文，返回有差异的条目列表供审阅展示。"""
    import difflib
    changes = []

    def _similar(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a.strip(), b.strip()).ratio()

    def _find_original(text: str) -> str:
        """在原文中找最相近的行。"""
        best, best_score = text, 0.0
        for line in resume_text.splitlines():
            s = _similar(text, line)
            if s > best_score:
                best_score, best = s, line
        return best if best_score > 0.3 else ""

    # 专业技能
    for cat, desc in profile.get("skills", {}).items():
        orig = _find_original(f"{cat}：{desc}")
        if orig and _similar(desc, orig) < 0.95:
            changes.append({"section": "skills", "label": cat,
                            "original": orig, "modified": f"{cat}：{desc}"})

    # 实习经历
    for job in profile.get("work_experience", []):
        label = f"{job.get('company', '')}  {job.get('title', '')}"
        for bullet in job.get("bullets", []):
            orig = _find_original(bullet)
            if orig and _similar(bullet, orig) < 0.95:
                changes.append({"section": "work_experience", "label": label,
                                "original": orig, "modified": bullet})

    # 项目经历
    for proj in profile.get("projects", []):
        label = proj.get("name", "")
        for bullet in proj.get("bullets", []):
            orig = _find_original(bullet)
            if orig and _similar(bullet, orig) < 0.95:
                changes.append({"section": "projects", "label": label,
                                "original": orig, "modified": bullet})

    return changes


_VERIFY_SYSTEM_PROMPT = """\
你是一位简历质量审核员。你会收到：原始简历文本、改写后的简历 JSON、岗位 JD。

你的任务是逐条检查 JSON 中 skills、work_experience、projects 的每一条 bullet，只修正以下两类问题：

【问题 A：编造事实】
判断标准：改写后出现了原文中完全没有提及的具体行动、成果或能力，候选人并没有做过这件事。
位置不限——无论在句中还是句末，只要是原文没有的新事实就必须删除。
典型情形：
- 原文描述了某项工作，改写后追加了原文没有的产出或影响（如原文只写"录入数据"，改写后加上"驱动业务增长"）
- 原文是某一行业/职能的经历，改写后引入了完全不同岗位的职责描述（如原文是客服岗，改写后加入了"系统架构设计""技术选型"等）
✗ 错误："负责录入产品数据，推动供应链降本增效闭环"（"供应链降本增效闭环"原文没有）
✓ 正确："负责录入产品数据，提升数据录入准确率"（措辞调整，未新增候选人没做过的事）

【问题 B：标签前缀被删除】
判断标准：原文 bullet 以「词语：」开头（如"数据分析："），改写后前缀消失。
修正：还原该标签前缀，保留改写后的正文内容。

【不需要修改】
- 措辞调整、关键词嵌入、语句重组——只要没有引入原文没有的具体事实

输出：返回修正后的完整 JSON 对象，格式与输入完全相同，不要任何其他文字。
"""


def _verify_profile(
    resume_text: str,
    profile: dict,
    jd: str,
    client,
    model: str,
) -> dict:
    """用第二次 LLM 调用检查并修正 profile 中的规则违反。"""
    user_msg = (
        f"【原始简历文本】\n{resume_text}\n\n"
        f"【改写后 JSON】\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n\n"
        f"【岗位描述】\n{jd}"
    )
    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _VERIFY_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    try:
        return _parse_ats_json(response.choices[0].message.content)
    except Exception:
        return profile  # 解析失败时保留原 profile


def call_llm_ats(jd: str, resume_text: str, client=None, model: str = None) -> tuple[dict, list]:
    """调用 LLM，返回 (profile, changes)。profile 为改写后完整内容，changes 由代码计算。"""
    if client is None or model is None:
        client, model = _get_client()
    user_msg = f"【岗位描述】\n{jd}\n\n【简历内容】\n{resume_text}"
    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _ATS_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    profile = _parse_ats_json(response.choices[0].message.content)
    profile = _verify_profile(resume_text, profile, jd, client, model)
    changes = compute_changes(profile, resume_text)
    return profile, changes


def call_llm_ats_with_feedback(
    jd: str,
    resume_text: str,
    prev_profile: dict,
    feedback: str,
    client=None,
    model: str = None,
) -> tuple[dict, list]:
    """基于用户反馈重新生成，返回 (profile, changes)。"""
    if client is None or model is None:
        client, model = _get_client()
    user_msg = (
        f"【岗位描述】\n{jd}\n\n"
        f"【简历内容】\n{resume_text}\n\n"
        f"【上一版生成结果】\n{json.dumps(prev_profile, ensure_ascii=False, indent=2)}\n\n"
        f"【用户反馈】\n{feedback}\n\n"
        "请根据用户反馈调整内容，重新输出完整 JSON 对象。"
    )
    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _ATS_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    profile = _parse_ats_json(response.choices[0].message.content)
    profile = _verify_profile(resume_text, profile, jd, client, model)
    changes = compute_changes(profile, resume_text)
    return profile, changes


# ──────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────

def tailor_resume(
    jd: str,
    output_name: str,
    modifications: list[dict],
    base_path: Path | None = None,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """将已确认的修改应用到 docx，返回输出文件路径。"""
    if base_path is None:
        base_path = _get_base_resume()
    user_name = _get_user_name()
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{user_name}简历_{output_name}版.docx"
    apply_modifications(base_path, modifications, output_path)
    return output_path
