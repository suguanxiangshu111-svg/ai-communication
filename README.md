# AI 智能伴侣 🤖💬

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?logo=streamlit&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-DeepSeek-4D6BFE)
![License](https://img.shields.io/badge/License-MIT-green)
![PRs](https://img.shields.io/badge/PRs-welcome-brightgreen)

<!-- 建议在这里放一张截图：<img src="docs/screenshot.png" width="720"> -->

一个基于 **Streamlit + DeepSeek** 的本地 AI 伴侣聊天应用。
除了情侣对话、流式输出、会话本地持久化之外，最大的特色是：

> **把你的微信/QQ 聊天记录（txt）丢进去，它会分析出对方的说话风格，自动生成一个语气一致、会说同样口头禅的 AI 伴侣。**

单文件项目，无需数据库，全部数据留在你自己的电脑上，API Key 只从环境变量读取。

---

## ✨ 核心特性

### 🆕 聊天记录导入（本项目的重点）
| 能力 | 说明 |
|---|---|
| 📄 上传 txt | 支持微信/QQ 导出的纯文本聊天记录（**不支持**数据库/加密文件/图片语音） |
| 🧠 自动解析 | 自动兼容 4 种常见导出格式，自动识别说话人与消息条数 |
| 🔍 风格分析 | 统计平均句长、短句占比、常用 emoji、口头禅、语气词、标点习惯 |
| 🤖 AI 生成性格 | 复用同一个 DeepSeek API，把统计特征 + 真实原话样本交给模型提炼人设 |
| ⚡ 自动填充 | 分析结果**直接覆盖**侧边栏【伴侣信息】的 `nick_name`（昵称）和 `nature`（性格） |
| ✏️ 仍可手改 | 自动填充后你依旧可以随时手动修改，输入框内容立即生效 |
| 🛟 本地兜底 | 没配 Key / 接口超时 / 返回格式错误时，自动降级为本地统计生成性格，功能不中断 |

### 💑 对话与记忆（原有功能，完整保留）
- **流式输出**：回复逐字显示，像真人打字
- **深度思考**：请求带 `reasoning_effort="high"` + `thinking` 参数
- **会话管理**：新建 / 加载 / 删除会话，左侧历史列表一键切换
- **本地持久化**：会话以 json 保存在 `sessions/` 目录，重启不丢
- **人设注入**：`system_prompt` 模板自动套用当前昵称与性格，导入后语气立刻对齐

---

## 🚀 快速开始

### 1. 环境要求
- Python **3.9+**（代码逻辑已在 Python 3.14 上完成测试；streamlit 本体对 3.14 的支持请以官方为准，稳妥起见可用 3.11 / 3.12）
- 建议使用最新版 `streamlit`（代码用了 `width="stretch"`，旧版本请改成 `use_container_width=True`）
- 建议使用最新版 `openai`（需要新版客户端才支持 `reasoning_effort` 参数）

```bash
pip install -U streamlit openai
```

### 2. 配置 API Key（不硬编码，由你自己管理）
Windows PowerShell：
```powershell
$env:DEEPSEEK_API_KEY = "sk-你的密钥"
```
macOS / Linux：
```bash
export DEEPSEEK_API_KEY="sk-你的密钥"
```
> 想永久生效可写进系统环境变量。密钥申请地址：<https://platform.deepseek.com>
>
> 客户端配置：`base_url="https://api.deepseek.com"`，对话与风格分析都使用 `model="deepseek-chat"`。

### 3. 运行
```bash
streamlit run ai_communication.py
```
浏览器会自动打开 <http://localhost:8501>

---

## 📖 使用指南

### 第一步：正常聊天
底部输入框直接说话即可。默认人设是「小甜甜 / 温柔开朗」。

### 第二步：导入聊天记录，让 AI 学会对方的语气

```
① 自己先把聊天记录导出为 txt   →   ② 侧边栏上传 txt
        ↓
③ 页面自动解析并识别"伴侣是哪一方"   →   ④ 点【分析记录生成性格】
        ↓
⑤ 昵称、性格被自动覆盖到【伴侣信息】   →   ⑥ 直接开始聊天（语气已对齐）
```

操作细节：
1. 打开侧边栏 **「导入聊天记录」** 模块（就在【伴侣信息】上方）
2. 点击上传按钮选择 `.txt` 文件 → 会自动提示 **上传成功 / 解析完成**（含消息条数、识别格式、文本编码）
3. 若记录里有两个人说话，会出现下拉框 **「记录里哪一方是伴侣（对方）？」**，默认已自动判断（会排除"我/自己"，QQ 记录还会优先读文件头部的 `消息对象`），判断错了可以手动切换
4. 点击 **「分析记录生成性格」** → 完成后弹出 toast，昵称与性格已写入侧边栏
5. 不满意可以**直接手动修改**昵称/性格输入框，改完立即生效

### 怎么把聊天记录导出成 txt？

| 平台 | 做法 |
|---|---|
| **QQ** | 官方支持：消息管理器 → 选中好友/群 → 右键「导出消息记录」→ 文件类型选 **文本文件(*.txt)** |
| **微信** | 官方 PC 端**没有**导出 txt 的功能。常见做法：① 用第三方本地导出工具导出为 txt；② 手动复制聊天内容粘贴进记事本另存为 `.txt` |

> ⚠️ **隐私提醒**：聊天记录只在你本机解析。但点击「分析记录生成性格」时，**抽取出的消息样本会发送给 DeepSeek 接口**用于分析风格（默认最多 400 条 / 6000 字）。介意的话请先自行脱敏，或把 `MAX_SAMPLE_CHARS` 调小。

### 会话管理
- **新建对话**：保存当前会话 → 清空 → 生成新会话名（同名时自动加 `_2` 后缀，不会覆盖旧记录）
- **加载会话**：点会话名按钮，历史消息与当时的昵称/性格一并恢复
- **删除会话**：点右侧 ❌

---

## 📄 支持的聊天记录格式

解析器按顺序自动尝试，命中即停，无需你手动选择格式：

| 格式 | 样例 | 说明 |
|---|---|---|
| 时间戳（时间在前）| `2024-03-01 21:03:12 小桃` ＋ 下一行内容 | 微信/QQ 文本导出主流格式，支持多行消息、`[图片]` 等标记 |
| 时间戳（昵称在前）| `小桃 2024-03-01 21:03:12` ＋ 下一行内容 | 部分工具导出格式 |
| 昵称: 内容 | `小桃: 在干嘛呀～` | 手动整理/复制粘贴的常见格式 |
| 逐行兜底 | 每行一条消息 | 无法识别说话人时使用（全部按"未知"说话人处理） |

**编码自动识别**：依次尝试 `UTF-8 BOM → UTF-8 → GB18030(GBK) → Big5 → UTF-16(BOM)`，全部失败则用容错模式并提示，不会因为编码问题乱码或崩页。

已自动忽略的系统噪音行：`====` 分隔线、`消息记录（此消息记录为文本格式…）`、`消息对象:xxx`、`消息分组`、`导出时间` 等。
QQ 昵称尾巴 `阿哲(10001)` 会自动清理；纯媒体标记（`[图片]` `[表情]` `[语音]` …）不会污染风格统计。

---

## ⚙️ 工作原理

```
┌──────────────┐   ┌───────────────┐   ┌──────────────────┐
│ 上传 txt      │ → │ 多编码解码     │ → │ 解析成对话列表     │
│ (max 20MB)   │   │ + 长文本截断   │   │ 说话人 / 时间 / 内容│
└──────────────┘   └───────────────┘   └────────┬─────────┘
                                                ↓
                                     ┌──────────────────────┐
                                     │ 判定"伴侣"是哪一方     │
                                     │ (排除我/自己, 读消息对象)│
                                     └──────────┬───────────┘
                                                ↓
        ┌───────────────────────────────────────┴──────────────────┐
        ↓ 成功                                                     ↓ 失败/无 Key
┌───────────────────────┐                              ┌────────────────────┐
│ DeepSeek 分析风格      │                              │ 本地统计兜底        │
│ 统计特征 + 均匀抽样原话 │                              │ 由统计数据拼性格描述 │
│ 返回 JSON 人设         │                              │                    │
└───────────┬───────────┘                              └─────────┬──────────┘
            └───────────────────┬────────────────────────────────┘
                                ↓
                  ┌──────────────────────────────┐
                  │ 覆盖 st.session_state         │
                  │   nick_name / nature         │
                  └──────────────┬───────────────┘
                                 ↓
                  ┌──────────────────────────────┐
                  │ system_prompt % (昵称, 性格)  │ → 对话语气与记录中的人一致
                  └──────────────────────────────┘
```

**对话接口参数（与原项目完全一致，未做改动）**
```python
client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "system", "content": system_prompt % (nick_name, nature)}, *messages],
    stream=True,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
```

**分析接口参数**
```python
client.chat.completions.create(
    model="deepseek-chat",              # 复用同一个客户端与 API Key
    messages=[{"role": "system", "content": ANALYSIS_SYSTEM_PROMPT}, {"role": "user", "content": 统计特征+样本}],
    stream=False, temperature=0.6, max_tokens=900,
    timeout=60,                          # 超时可捕获
    response_format={"type": "json_object"},   # 要求返回 JSON，便于回填昵称/性格
)
```

---

## 🔧 可调参数

都在文件开头的常量区，改完重启即可：

| 常量 | 默认值 | 作用 |
|---|---|---|
| `MAX_UPLOAD_BYTES` | `20 MB` | 上传文件大小上限 |
| `MAX_RECORD_CHARS` | `300_000` | 解析文本长度上限（防超长文本卡死） |
| `MAX_SAMPLE_CHARS` | `6000` | 送进模型的样本字符上限（**控制隐私与费用**） |
| `MAX_SAMPLE_TURNS` | `400` | 送进模型的样本条数上限 |
| `ANALYSIS_TIMEOUT` | `60`（秒） | 分析接口超时时间 |

**system_prompt 模板**（`%s` 两个占位符顺序 = 昵称、性格，改动时别删占位符）：
```python
你叫%s,是用户的伴侣
1. 每次只输出 1 条消息
2.要体现%s的性格
3. 和用户说话语气对齐
4. 回复简短，模仿微信聊天，不要大段长文
5. 可以适度加 ❤✨这类 emoji
6. 说话符合情侣身份
7. 性格描述里提到的语气词、口头禅、常用 emoji、句子长短和标点习惯，都要在回复里真实体现出来
8. 严禁书面语和客服腔，像真人发微信一样自然聊天
```

---

## 📁 项目结构

```
ai communication/
├── ai_communication.py          # 主程序（单文件，约 900 行，含完整中文注释）
├── sample_wx_chat.txt           # 示例微信聊天记录，可直接上传体验
├── sessions/                    # 会话持久化目录（自动创建）
│   └── 2026-09-13 21_29_56.json # 单个会话：nick_name / nature / current_session / messages
└── _tests/                      # 离线测试（不需要可整个删除）
    ├── fakes.py                 # streamlit / openai 替身 + 测试样本
    ├── test_chat_import.py      # 45 项：解码/解析/统计/JSON 容错
    └── test_app_flow.py         # 63 项：上传→分析→填充→对话→会话管理 全流程
```

会话 json 结构：
```json
{
  "nick_name": "软糯小桃",
  "nature": "语气软糯爱撒娇，句尾几乎必带“呀、啦、嘛”…；风格关键词：软糯撒娇…；常用原话：「在干嘛呀～」…",
  "current_session": "2026-09-13 21_29_56",
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "嗨～你来啦！在干嘛呀～ 🥰"}
  ]
}
```

---

## ❓ 常见问题

**Q：提示"没有检测到环境变量 DEEPSEEK_API_KEY"？**
A：环境变量没生效。确认是在**同一个终端**里 set 后再 `streamlit run`；改过系统环境变量需要重开终端。此时导入功能会自动走本地统计兜底，仍可用。

**Q：上传后提示"文件格式有误"或"没有解析出对话内容"？**
A：确认文件是 `.txt` 纯文本、内容不为空、由微信/QQ 直接导出。如果只是自己手打的普通文章而非对话，解析器识别不到说话人时会给出提示。

**Q：为什么昵称/性格不是我想要的？**
A：模型是从记录里提炼的，可以直接在【伴侣信息】手动改；也可以在「记录里哪一方是伴侣」下拉框里切换另一方后重新分析。

**Q：导入后聊天语气还是很书面？**
A：性格描述越具体，语气越像。可以手动在性格里补一句，例如"每句话不超过 12 个字，必带一个 emoji"。

**Q：分析长聊天记录会不会很贵？**
A：不会。样本默认最多 400 条 / 6000 字（均匀抽样 + 硬截断），单次分析是普通非流式请求。

**Q：支持微信数据库 / 加密的 .dat 文件吗？**
A：**不支持**，本项目只解析纯文本 txt。界面里也做了提示。

---

## ☁️ 上传到 GitHub

仓库里已备好 `.gitignore` 与 `requirements.txt`，直接按下面几步即可发布。

### 🔒 推送前必读（隐私）

`sessions/` 目录里是**你真实的情侣对话记录**，`.gitignore` 已把它排除。推送前请务必确认它没被提交：

```bash
git status              # sessions/ 不应该出现在列表里
git ls-files            # 确认没有 sessions/ 下的文件
```

> 建议把仓库设为 **Private**。如果不小心提交过聊天记录，执行
> `git rm -r --cached sessions` 后再提交，并考虑重写历史（`git filter-repo`）。

### 发布步骤

```bash
cd "E:/ai communication"

git init
git add .
git commit -m "feat: AI 智能伴侣 —— 支持微信/QQ聊天记录导入自动生成性格"
git branch -M main

# 先在 GitHub 网页上新建一个空仓库（不要勾选 Add README），然后：
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

### 会被提交的文件

```
ai_communication.py     # 主程序
README.md               # 本说明
LICENSE                 # MIT 开源协议
requirements.txt        # 依赖
.gitignore              # 忽略规则
.gitattributes          # 统一换行符
sample_wx_chat.txt      # 示例聊天记录（虚构内容，可安全公开）
_tests/                 # 离线测试（3 个文件）
```

### 首次推送前：设置你的 git 身份

如果这台机器还没配过 git 身份，先设置一次（否则 `git commit` 会失败）：

```bash
git config --global user.name  "你的名字"
git config --global user.email "你的邮箱@example.com"
```

> 仓库本地已临时设置为占位身份 `ai-communication@users.noreply.github.com`。
> 想改成你自己，在**推送前**执行（推送后就不好改了）：
> ```bash
> git config user.name "你的名字"
> git config user.email "你的邮箱@example.com"
> git commit --amend --reset-author --no-edit
> ```
> 同时记得把 `LICENSE` 第 3 行的 `<你的名字或 GitHub 用户名>` 换成你的名字。

### 不会被提交的内容

| 排除项 | 原因 |
|---|---|
| `sessions/` | **你的真实聊天记录** |
| `__pycache__/`、`.venv/` | 编译缓存与虚拟环境 |
| `.env`、`secrets.toml`、`*_api_key*` | 密钥类文件 |
| `_tests/_workdir/` | 测试产生的临时会话 |

### 别人克隆后怎么跑

```bash
git clone https://github.com/<你的用户名>/<仓库名>.git
cd <仓库名>
pip install -r requirements.txt
# 配置自己的密钥（仓库里没有、也不该有密钥）
$env:DEEPSEEK_API_KEY = "sk-你自己的密钥"      # Windows
export DEEPSEEK_API_KEY="sk-你自己的密钥"      # macOS / Linux
streamlit run ai_communication.py
```

---

## 🧪 测试

项目自带离线测试（用行为等价的 `streamlit` / `openai` 替身，无需联网、无需 API Key）：

```bash
python _tests/test_chat_import.py    # 45/45 通过
python _tests/test_app_flow.py       # 63/63 通过
```

覆盖：四种格式解析、四种编码、空文件/超大文件/二进制乱码、50 万字符长文本、自动填充昵称性格、手动覆盖、流式输出、会话保存/加载/删除、API 超时与非法 JSON 降级、密钥读取与无硬编码。

---

## ⚠️ 注意事项与免责声明

- **仅供个人学习与本地娱乐使用**，请勿用于冒充他人、骚扰或任何违法用途。
- 导出的聊天记录包含**他人隐私**，请自行妥善保管；样本会发送至 DeepSeek 接口，请自行评估并做好脱敏。
- 请遵守微信/QQ 的用户协议，仅导出**你本人有权处理**的聊天内容。
- API 费用由使用者自行承担；请勿把密钥提交到 Git 仓库或分享给他人。

---

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 开源，你可以自由使用、修改、分发，甚至商用，只需保留版权声明。
软件按"原样"提供，不附带任何担保。

> 使用前请再次阅读上文的免责声明：请仅导入你本人有权处理的聊天内容，并妥善保护他人隐私。

---

## 📜 技术栈

`Python` · `Streamlit`（Web UI 与状态管理）· `OpenAI SDK`（调用 DeepSeek 兼容接口）· `DeepSeek Chat`（对话与风格分析）· `re` / `Counter`（聊天记录解析与风格统计）· `JSON`（会话持久化）
