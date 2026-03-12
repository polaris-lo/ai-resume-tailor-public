# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 重要：Claude Code 工作方式

**除非特别说明，所有需要 LLM 的任务（简历定制、JD 分析等）直接由 Claude Code 本身完成，不调用外部 API、不查找 API Key、不运行 Python 脚本调用 LLM SDK。**

具体做法：
- 简历定制：Claude Code 直接读取简历 + JD，生成修改建议，再调用 Python 脚本仅做 docx 写入

## 简历定制规则

**原创性校验（每次必须遵守）**：在生成修改建议时，凡是原始简历中未明确提及的具体指标、工具、项目经历、方法论，必须在展示建议前单独列出并询问用户是否做过，确认后才可写入。不得直接加入。

- 示例需询问的内容：特定数据指标（如 CSAT、DAU、GMV）、特定工具（如 Tableau、Figma）、特定经历（如"主导过 A/B 测试"）
- 对原有内容的角度重新包装（如将"收集反馈"改写为"用户洞察"）无需询问，属于正常提炼

## 项目用途

简历定制工具，核心功能：输入岗位 JD → 由 LLM 分析 → 输出定制版 Word 简历。

## 首次使用

```bash
python setup.py   # 配置姓名、简历路径、LLM API Key
```

## 运行命令

```bash
# 根据 JD 生成定制版简历
cd resume_tailor
python main.py "JD文本内容" --name "AI产品经理"
python main.py --jd-file jd.txt --name "数据分析师"
# 输出：../output/<姓名>简历_<岗位名>版.docx
```

## 目录结构

```
ai-resume-tailor-public/
├── setup.py              首次运行配置向导
├── config.py             配置加载模块（读取 ~/.resume-tailor/config.json）
├── output/               所有生成版本
└── resume_tailor/
    ├── main.py           CLI 入口
    └── src/
        └── resume_tailor.py    核心逻辑（读取段落 → 调 LLM → 修改 docx）
```

## 核心架构

### resume_tailor

读取基础简历所有段落（带 index），通过 OpenAI 兼容 API 分析 JD 匹配点，返回 JSON 修改列表：
```json
[{"para_index": N, "reason": "...", "segments": [{"text": "...", "bold": bool}]}]
```
然后 `apply_modifications` 复制基础简历，按 `para_index` 精确替换段落内容，同时清理空段落和嵌入 `sectPr`。

用户配置存储在 `~/.resume-tailor/config.json`（项目外，不提交）：
```json
{
  "user_name": "姓名",
  "resume_path": "~/my-resume.docx",
  "llm": { "api_key": "...", "base_url": "...", "model": "..." }
}
```

## 简历 docx 格式规范

修改简历文件时必须遵守：

- **字体**：宋体五号（10.5pt）。`w:ascii`/`w:hAnsi`/`w:eastAsia`/`w:cs` 均设为宋体
- **加粗**：只加粗关键词（技能类别名、条目类型词、关键数字），不整句加粗
- **空段落**：删除所有 `text.strip() == ''` 的段落
- **嵌入分节符**：删除所有 `pPr` 内的 `sectPr`，保留 body 末尾唯一的 sectPr
- **PDF 转换**：由用户手动从 Word 导出，不要自动执行
- **简历文字**：全部使用中文，不加英文对照

设置 run 字体的标准写法：
```python
run.font.size = Pt(10.5)
rPr = run._r.get_or_add_rPr()
rFonts = rPr.get_or_add_rFonts()
for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
    rFonts.set(qn(attr), "宋体")
```

## 安全注意事项

- `*.docx`、`*.pdf` 均在 `.gitignore` 中排除，不得提交
- 用户配置（含 API Key）存储在 `~/.resume-tailor/`（项目目录外）

## Slash Commands

| 命令 | 定义文件 | 功能 |
|------|----------|------|
| `/resume-tailor` | `.claude/commands/resume-tailor.md` | 根据 JD 生成定制版简历 |
| `/boss-greet` | `.claude/commands/boss-greet.md` | 生成 BOSS 直聘打招呼消息 |
