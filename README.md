# 简历定制工具

输入岗位 JD，自动生成针对性修改建议，交互确认后输出定制版 Word 简历（.docx）。

## 三种使用方式

| | Web 模式 | CLI 模式 | Claude Code 模式 |
| --- | --- | --- | --- |
| **适合人群** | 所有用户（推荐） | 偏好命令行的用户 | 已安装 Claude Code 的用户 |
| **需要 API Key** | 是 | 是 | 否，由 Claude 直接分析 |
| **交互方式** | 浏览器页面 | 终端命令行 | slash command |
| **首次配置** | 无需配置，页面填写 | 需要运行 `python setup.py` | 无需额外配置 |

---

## 环境要求

- Python 3.10+

---

## 第零步：下载项目文件

### 方式一：下载 ZIP

前往 [项目页面](https://github.com/polaris-lo/ai-resume-tailor-public) 下载文件到本地。

### 方式二：git clone

```bash
git clone https://github.com/polaris-lo/ai-resume-tailor-public.git ~/Documents/ai-resume-tailor-public
```

---

## 首次安装依赖

> 注意：所有命令都需要先进入项目文件夹后再运行，否则会提示"找不到文件"。

```bash
# 第一步：进入项目文件夹（路径改成你自己电脑上的实际位置）
# macOS / Linux：
cd ~/Documents/ai-resume-tailor-public
# Windows（命令提示符）：
# cd %USERPROFILE%\Documents\ai-resume-tailor-public

# 第二步：安装依赖（只需安装一次）
pip install -r requirements.txt
```

如果提示 `No such file or directory: 'requirements.txt'`，说明还没有进入项目文件夹，请先执行第一步。

---

## 方式一：Web 模式（推荐）

### 启动

```bash
# 进入项目文件夹（已进入则跳过）
# macOS / Linux：cd ~/Documents/ai-resume-tailor-public
# Windows：cd %USERPROFILE%\Documents\ai-resume-tailor-public

# 启动 Web 界面
streamlit run app.py
```

浏览器会自动打开。在页面中：

1. 左侧填写 API 配置（选择服务商，填写 API Key）
2. 上传基础简历（.docx）并粘贴 JD
3. 点击「分析」查看修改建议，可输入意见让 LLM 重新生成
4. 确认后点击下载按钮获取定制版 Word 简历

API Key 仅在当前 session 内存中使用，不会被存储。

---

## 方式二：CLI 模式

### 第一步：配置

```bash
# 进入项目文件夹（已进入则跳过）
# macOS / Linux：cd ~/Documents/ai-resume-tailor-public
# Windows：cd %USERPROFILE%\Documents\ai-resume-tailor-public

python setup.py
```

按提示填写：
- 您的姓名（用于输出文件命名）
- 基础简历路径（.docx 文件）
- LLM 服务商、API Key、模型名称

配置保存在 `~/.resume-tailor/config.json`，不会提交到 git。

支持的 API 服务商：

| 服务商 | Base URL | 示例模型 |
|--------|----------|----------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-max` |
| 其他兼容接口 | 自定义 | 自定义 |

### 第二步：生成定制简历

```bash
cd resume_tailor

# 直接粘贴 JD 文本
python main.py "岗位描述文本..." --name "产品经理"

# 从文件读取 JD
python main.py --jd-file jd.txt --name "数据分析师"

# 不指定岗位名称时自动推断
python main.py --jd-file jd.txt
```

工具会展示修改建议，等待您确认或输入修改意见后再生成文件。

**输出路径**：`output/<姓名>简历_<岗位名称>版.docx`

---

## 方式二：Claude Code 模式

已安装 [Claude Code](https://claude.ai/code) 的用户可直接使用 slash command，无需 API Key，由 Claude 本身完成 JD 分析。

在项目目录下打开 Claude Code，输入：

```
/resume-tailor   # 根据 JD 生成定制版简历
/boss-greet      # 生成 BOSS 直聘打招呼消息
```

Claude Code 会引导您完成后续步骤。

---

## 导出 PDF

在 Word 中打开生成的 .docx，手动导出为 PDF。

## 目录结构

```
├── app.py                Web 界面入口（streamlit run app.py）
├── setup.py              首次配置向导（CLI 模式使用）
├── config.py             配置加载模块
├── requirements.txt      依赖列表
├── output/               生成的定制版简历（已在 .gitignore 中排除）
└── resume_tailor/
    ├── main.py           CLI 入口
    └── src/
        └── resume_tailor.py  核心逻辑
```

## 简历格式要求

基础简历需为 .docx 格式，段落样式使用标准 Word 样式：

- 节标题段落使用 `Normal` 样式
- 内容行使用 `列出段落1` 样式
