#!/usr/bin/env python3
"""
简历定制工具

用法：
  python main.py "JD文本内容" --name "岗位名称"
  python main.py --jd-file jd.txt --name "数据分析师"
  python main.py "JD文本内容"          # 不指定名称时自动推断

输出：../output/<姓名>简历_<岗位名称>版.docx

首次使用请先运行：python ../setup.py
"""

import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

app = typer.Typer(
    help="根据岗位 JD 自动生成针对性简历（Word 排版格式）",
    add_completion=False,
)


@app.command()
def tailor(
    jd: str = typer.Argument("", help="岗位描述文本（直接粘贴）"),
    name: Optional[str] = typer.Option(None, help="岗位名称，用于文件命名，如 AI产品经理（不指定则自动推断）"),
    jd_file: Optional[Path] = typer.Option(None, help="从 .txt 文件读取 JD（与直接输入二选一）"),
    base: Optional[Path] = typer.Option(None, help="基础简历路径（默认读取 setup.py 中配置的路径）"),
):
    """
    根据岗位描述，调用 LLM 分析匹配点，交互确认后生成定制版简历 .docx。

    \b
    工作流：
      1. 此工具 → 展示修改建议 → 用户确认 → 生成岗位定制版 Word 简历
      2. 手动检查并微调输出的 .docx
      3. 手动从 Word 导出 PDF
    """
    from config import load_config
    from src.resume_tailor import (
        call_llm,
        call_llm_with_feedback,
        format_modifications,
        generate_greeting,
        get_resume_content,
        suggest_job_name,
        tailor_resume,
        _get_base_resume,
        _get_user_name,
    )

    # 读取配置
    try:
        cfg = load_config()
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    # 读取 JD
    if jd_file:
        if not jd_file.exists():
            typer.echo(f"找不到 JD 文件：{jd_file}", err=True)
            raise typer.Exit(1)
        jd = jd_file.read_text(encoding="utf-8")

    if not jd.strip():
        typer.echo("错误：请提供岗位描述（直接输入或 --jd-file）", err=True)
        raise typer.Exit(1)

    base_path = base or _get_base_resume()
    if not base_path.exists():
        typer.echo(f"找不到基础简历：{base_path}", err=True)
        typer.echo("请检查 setup.py 中配置的 resume_path 是否正确。", err=True)
        raise typer.Exit(1)

    # 自动推断岗位名称
    if not name:
        typer.echo("未指定岗位名称，正在从 JD 自动推断...")
        name = suggest_job_name(jd)
        typer.echo(f"推断岗位名称：{name}\n")

    user_name = _get_user_name()
    typer.echo(f"基础简历：{base_path.name}")
    typer.echo(f"目标岗位：{name}\n")

    # 读取简历内容
    typer.echo("正在读取基础简历...")
    resume_paras = get_resume_content(base_path)

    # 调用 LLM 生成初版修改建议
    typer.echo("正在调用 LLM 分析 JD 并生成修改建议...\n")
    modifications = call_llm(jd, resume_paras)

    # 交互确认循环
    while True:
        typer.echo("─" * 60)
        typer.echo(format_modifications(modifications, resume_paras))
        typer.echo("─" * 60)
        typer.echo(f"输出文件将命名为：{user_name}简历_{name}版.docx\n")
        typer.echo("确认生成？")
        typer.echo("  直接回车        → 确认，生成 docx")
        typer.echo("  输入修改意见    → 重新生成建议")
        typer.echo("  q               → 放弃退出")

        answer = input("> ").strip()

        if answer == "":
            break
        elif answer.lower() == "q":
            typer.echo("已取消。")
            raise typer.Exit(0)
        else:
            typer.echo("\n正在根据您的意见重新生成修改建议...\n")
            modifications = call_llm_with_feedback(jd, resume_paras, modifications, answer)

    # 生成 docx
    output = tailor_resume(jd, name, modifications, base_path=base_path)
    typer.echo(f"\n输出文件：{output.resolve()}")
    typer.echo("请在 Word 中打开检查后，手动导出 PDF。")

    # 可选：生成打招呼消息
    typer.echo("\n是否需要生成 BOSS 直聘打招呼消息？(y/N) ", nl=False)
    if input().strip().lower() == "y":
        typer.echo("\n正在生成打招呼消息...\n")
        greeting = generate_greeting(jd, resume_paras)
        typer.echo("─" * 60)
        typer.echo(greeting)
        typer.echo("─" * 60)


if __name__ == "__main__":
    app()
