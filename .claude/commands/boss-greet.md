根据用户提供的岗位 JD 和用户的简历内容，生成一条 BOSS 直聘打招呼消息。

首先运行以下命令读取用户简历内容：

```bash
# macOS/Linux 用 python3，Windows 用 python
python3 -c "
import sys; sys.path.insert(0, '.')
from config import load_config
from resume_tailor.src.resume_tailor import get_resume_content, _build_resume_str
from pathlib import Path
cfg = load_config()
print(_build_resume_str(get_resume_content(Path(cfg['resume_path']).expanduser())))
"
```

写作规则：
1. 开头一句介绍身份（从简历中提取：求职者身份 + 专业方向）
2. 列出 2～4 个与 JD 最匹配的技能点，括号内注明在哪段经历中用过（从简历中提取，保持真实）
3. 结尾一句表达兴趣，邀请进一步沟通
4. 总字数 100 字以内，语气真诚自然，全部中文

**只输出消息正文，不输出任何解释或其他内容。**

如果用户没有提供 JD，询问："请提供岗位 JD。"
