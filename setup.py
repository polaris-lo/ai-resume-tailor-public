"""
首次使用配置向导。
运行：python setup.py
"""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".resume-tailor"
CONFIG_PATH = CONFIG_DIR / "config.json"

PRESET_APIS = {
    "1": ("OpenAI", "https://api.openai.com/v1", "gpt-4o"),
    "2": ("DeepSeek", "https://api.deepseek.com", "deepseek-chat"),
    "3": ("Qwen（通义千问）", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-max"),
    "4": ("自定义", "", ""),
}


def prompt(question: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    answer = input(f"{question}{hint}: ").strip()
    return answer if answer else default


def main():
    print("=" * 50)
    print("  简历定制工具 — 初始配置向导")
    print("=" * 50)
    print()

    # 已有配置则询问是否覆盖
    if CONFIG_PATH.exists():
        overwrite = input("检测到已有配置，是否重新配置？(y/N) ").strip().lower()
        if overwrite != "y":
            print("保留现有配置，退出。")
            return

    # 1. 用户姓名
    print("\n【基本信息】")
    user_name = prompt("您的姓名（用于输出文件命名）")
    if not user_name:
        print("姓名不能为空，退出。")
        return

    # 2. 简历路径
    resume_path = prompt("基础简历路径（.docx 文件）", "~/my-resume.docx")

    # 3. LLM API
    print("\n【LLM API 配置】")
    print("请选择 API 服务商：")
    for k, (name, _, _) in PRESET_APIS.items():
        print(f"  {k}. {name}")
    choice = prompt("输入编号", "1")
    provider_name, default_base_url, default_model = PRESET_APIS.get(choice, PRESET_APIS["4"])

    api_key = prompt("API Key")
    if not api_key:
        print("API Key 不能为空，退出。")
        return

    base_url = prompt("Base URL", default_base_url)
    model = prompt("模型名称", default_model)

    config = {
        "user_name": user_name,
        "resume_path": resume_path,
        "llm": {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
        },
    }

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"\n配置已保存至：{CONFIG_PATH}")
    print("\n下一步：")
    print("  cd resume_tailor")
    print('  python main.py --jd-file jd.txt --name "目标岗位名称"')
    print()


if __name__ == "__main__":
    main()
