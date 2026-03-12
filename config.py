"""
用户配置加载模块。
配置存储在 ~/.resume-tailor/config.json，首次使用请运行 python setup.py。
"""

import json
import os
from pathlib import Path

CONFIG_PATH = Path.home() / ".resume-tailor" / "config.json"


def load_config() -> dict:
    """加载用户配置，若不存在则提示运行 setup.py。"""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"未找到配置文件：{CONFIG_PATH}\n"
            "请先运行：python setup.py"
        )
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    required = ["user_name", "resume_path", "llm"]
    for key in required:
        if key not in cfg:
            raise ValueError(f"配置缺少字段：{key}，请重新运行 python setup.py")

    llm_required = ["api_key", "base_url", "model"]
    for key in llm_required:
        if key not in cfg["llm"]:
            raise ValueError(f"配置 llm 缺少字段：{key}，请重新运行 python setup.py")

    # 展开 ~ 路径
    cfg["resume_path"] = str(Path(cfg["resume_path"]).expanduser())
    return cfg
