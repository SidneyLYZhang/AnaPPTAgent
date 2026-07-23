# CLI 使用指南

## 前置条件

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) 包管理器
- 全局模型配置文件 `~/.anappt/models.yaml`

## 命令一览

AnaPPTAgent 的 CLI 入口为 `anappt`，支持以下子命令：

| 命令 | 说明 |
|------|------|
| `anappt` | 无参数时显示帮助信息 |
| `anappt new [<name>] [--no-skill] [--registry <url>]` | 创建新分析项目；不带 `<name>` 时原地初始化当前目录，带 `<name>` 时在当前目录下创建同名子目录 |
| `anappt init [<name>] [--no-skill] [--registry <url>]` | 创建新分析项目（`new` 的别名）；同样支持不带名字原地初始化当前目录 |
| `anappt run` | 启动或恢复流水线 |
| `anappt resume` | 从当前状态恢复流水线 |
| `anappt status` | 显示所有阶段状态 |
| `anappt config show` | 显示当前完整有效配置（含 thinking、web 搜索/读取，API key 掩码，标注来源） |
| `anappt config set` | 交互式配置三个模型角色（含 thinking）与 web_search/web_fetch 能力 |
| `anappt interactive` | 启动交互模式 |
| `anappt setup [--dir <path>] [--registry <url>]` | 检查环境并安装/更新 dashi-ppt-skill |

## 全局配置文件

!!! info "完整配置指引"
    详见 [配置指引](configuration.md)。

全局模型配置文件位于 `~/.anappt/models.yaml`（**所有配置集中在此文件,不再支持项目级覆盖**），定义三种模型角色与可选的 web 能力：

```yaml
reasoning:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}
  # thinking 缺省 → 使用模型最大思考强度

analysis:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: ${ANTHROPIC_API_KEY}
  thinking: FALSE              # 显式关闭思考

writing:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}
  # thinking 缺省 → 使用模型最大思考强度

# Web 搜索（可选段,缺省使用 DuckDuckGo,无需 key）
web_search:
  backend: anysearch                       # 可选: duckduckgo | anysearch | zai
  anysearch_api_key: ${ANYSEARCH_API_KEY}  # 可选,环境变量优先于 yaml
  zai_api_key: ${ZAI_API_KEY}              # 可选,环境变量优先于 yaml

# Web 读取（可选段,缺省禁用）
web_fetch:
  jina_api_key: ${JINA_API_KEY}            # 可选,环境变量优先于 yaml
```

**字段说明**：

- `thinking`（可选）：控制该角色调用 LLM 时的思考强度。
  - 字段缺省 → 使用模型最大思考强度（对已知 provider 主动传"最大"参数,如 OpenAI o-series 的 `reasoning_effort="high"`）
  - 字符串 `FALSE`（大小写不敏感,也接受 `False`/`false`/`OFF`/`off`）→ 关闭思考
  - `low`/`medium`/`high` → 按指定强度调用（如 OpenAI 映射为 `reasoning_effort`）
  - 整数 N → 作为 `budget_tokens` 传递给支持的 provider（如 Anthropic）
- `web_search` / `web_fetch` 为可选段,缺省时：Web 搜索使用 DuckDuckGo（无需 key）,Web 读取禁用。
- **环境变量优先于 models.yaml 中的对应字段**：当环境变量与 yaml 同时配置同一项时,以环境变量的值为准。

| 角色 | 阶段 | 用途 |
|------|------|------|
| reasoning | S1-S2 | 选题定义、数据需求分析 |
| analysis | S4 | 数据分析（工具调用） |
| writing | S5-S6 | 报告撰写、PPT 生成 |

支持所有 litellm 兼容的 provider（OpenAI、Anthropic、DeepSeek、Azure 等）。

## 项目配置文件

每个分析项目根目录下有一个 `report.yaml` 配置文件，字段说明如下：

```yaml
project:
  name: ""           # 项目名称
  type: "one_time"   # 项目类型：one_time | monthly | quarterly
  created: ""        # 创建日期（自动生成）

report:
  topic: ""          # 分析选题
  motivation: ""     # 为什么要做这个分析
  audience: []       # 目标受众列表
  objectives: []     # 分析目标
  success_criteria: []  # 成功标准

delivery:
  ppt_pages: "15-20"       # 期望的 PPT 页数
  formats: ["pptx", "html"]  # 输出格式
  theme_preference: null   # PPT 主题，null = 在 S6 阶段交互选择
```

### 字段详解

| 字段 | 类型 | 说明 |
|------|------|------|
| `project.name` | string | 项目名称，用于标识 |
| `project.type` | string | 项目类型：`one_time`（一次性）、`monthly`（月报）、`quarterly`（季报） |
| `project.created` | string | 创建日期，由 `anappt new` 自动填入 |
| `report.topic` | string | 分析选题，描述要分析的内容 |
| `report.motivation` | string | 做这个分析的动机和背景 |
| `report.audience` | list | 目标受众，如管理层、技术团队等 |
| `report.objectives` | list | 分析目标列表 |
| `report.success_criteria` | list | 成功标准，用于衡量分析质量 |
| `delivery.ppt_pages` | string | 期望的 PPT 页数范围，如 `"15-20"` |
| `delivery.formats` | list | 输出格式列表，支持 `pptx` 和 `html` |
| `delivery.theme_preference` | string/null | PPT 主题，设为 `null` 在 S6 阶段交互选择 |

!!! note "report.yaml 的生成与覆盖"
    `anappt new`/`init` 拷贝的 `report.yaml` 仅为**占位模板**。进入流水线后，S1 阶段会通过对话与 LLM 共同生成或精炼 `report.yaml`（经由 `write_artifact` 工具写回项目根），覆盖模板中的占位字段。因此模板值仅供初始化参考，最终生效内容以 S1 产出为准。

## 环境变量

| 环境变量 | 说明 |
|---------|------|
| `OPENAI_API_KEY` | OpenAI API 密钥 |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `ANYSEARCH_API_KEY` | AnySearch Web 搜索后端密钥。**环境变量优先于 models.yaml 中的 `web_search.anysearch_api_key`**；两者均未配置时回退 DuckDuckGo |
| `ZAI_API_KEY` | z.ai（智谱）Web 搜索后端密钥。**环境变量优先于 models.yaml 中的 `web_search.zai_api_key`** |
| `WEB_SEARCH_BACKEND` | 显式指定搜索后端,取值 `duckduckgo` / `anysearch` / `zai`。**环境变量优先于 models.yaml 中的 `web_search.backend`**；未配置时基于可用 key 自动选择；无任何 key 时始终使用 DuckDuckGo |
| `JINA_API_KEY` | Jina Reader API 密钥,用于网页读取。**环境变量优先于 models.yaml 中的 `web_fetch.jina_api_key`**；两者均未配置时 web 读取禁用 |
| `HTTP_PROXY` | HTTP 代理地址 |
| `HTTPS_PROXY` | HTTPS 代理地址 |
| `ALL_PROXY` | 全局代理地址（支持 socks5） |
| `LANG` | 语言选择：`zh_CN.UTF-8`（默认）或 `en_US.UTF-8` |

> **优先级提示**：对于 web 搜索与 web 读取,统一遵循 **环境变量 > models.yaml > 默认值** 的优先级。未设置环境变量时回退到 models.yaml,两者均未配置时使用默认值（DuckDuckGo 搜索 / 禁用 web 读取）。

## 命令示例

### 创建新项目

```bash
# 创建名为 my_report 的新项目（在当前目录下创建 my_report/ 子目录）
anappt new my_report

# 使用 init 别名
anappt init my_report

# 不带名字：原地初始化当前目录（不创建子目录）
anappt init

# 跳过 dashi-ppt-skill 下载
anappt new my_report --no-skill

# 指定 npm 镜像（加速 skill 下载）
anappt new my_report --registry https://registry.npmmirror.com
```

创建后生成如下目录结构：

```
my_report/
├── report.yaml                  # 项目配置（占位模板，S1 会覆盖）
├── .gitignore
├── data/
│   └── README.md
├── output/
│   ├── final_report.md          # S5 输出：分析报告
│   ├── images/
│   └── ppt/
│       ├── goal.json            # S6 中间产物：LLM 构造的幻灯片结构
│       ├── presentation.pptx    # S6 可选产物：PPTX（当 formats 含 pptx 时）
│       └── presentation.html    # S6 输出：HTML 幻灯片
└── .anappt/
    ├── state.yaml               # 项目初始化标记
    ├── memory.md                # 跨阶段共享记忆（LLM 维护）
    ├── s1_topic.md
    ├── s2_data_requirement.md
    ├── s3_data_profile.md
    ├── s4_analysis_report.md
    └── session_history/
        └── 2024-12-01_S1.md     # 按“日期_阶段”命名的会话日志
```

### 运行流水线

```bash
# 在项目目录中运行
cd my_report
anappt run
```

进入**对话式 TUI**后，由 LLM 多轮对话驱动各阶段产出（选题、数据需求、分析、报告、PPT 等）。每个阶段完成后，通过 `/confirm` 元命令推进到下一阶段；可随时输入自由文本与 LLM 对话、要求修改或补充。

### 恢复流水线

```bash
# 从上次中断处恢复
anappt resume
```

### 查看状态

```bash
# 显示所有阶段的状态
anappt status
```

输出示例：

```
ID | Name                      | Status          | Iter
---+---------------------------+-----------------+-----
S1 | Topic & Goal Definition   | completed       | 1
S2 | Data Requirement Analysis | completed       | 1
S3 | Data Loading & Validation | completed       | 1
S4 | Data Analysis             | awaiting_review | 2
S5 | Report Generation         | pending         | 0
S6 | PPT Generation            | pending         | 0
```

状态取值：`pending`（未开始）、`in_progress`（运行中）、`awaiting_review`（等待用户确认）、`completed`（已完成）。

### 配置模型

```bash
# 显示当前模型配置
anappt config show

# 交互式配置模型
anappt config set
```

`config show` 显示当前**有效配置**（env > yaml > 默认值的合并结果），包含三个角色（含 `thinking` 字段）、`web_search` 段（有效 backend 与各 key 是否已配置）、`web_fetch` 段（jina_api_key 是否已配置）。所有 `api_key`/`*_api_key` 字段做掩码（`${VAR}` 字面量原样显示,实际值显示 `****<末4位>`,空值显示 `<unset>`），并在字段后标注来源（`(env)` / `(yaml)` / `(default)`）。

`config set` 会引导用户逐一配置 reasoning、analysis、writing 三种模型角色的 provider、model、api_base（可选）、api_key 与 `thinking`（可选,直接回车跳过 = 缺省最大思考）；并在三角色配置完成后询问是否配置 `web_search` 与 `web_fetch` 段（可全部跳过以保持默认）。配置写入 `~/.anappt/models.yaml`（**不**在项目目录下生成任何 `models.yaml`）。

### 安装 dashi-ppt-skill

```bash
# 检查环境并安装/更新 dashi-ppt-skill
anappt setup

# 指定 skill 安装父目录
anappt setup --dir /path/to/skills

# 指定 npm 镜像地址
anappt setup --registry https://registry.npmmirror.com
```

`anappt setup` 会检查 Node.js ≥ 20、npm、Chrome（可选），然后通过 `npx dashi-ppt-skill@latest --dir <path>` 安装 skill 到 `~/.anappt/skills/dashi-ppt/`。

### 交互模式

```bash
# 启动对话式 TUI（必须在项目目录中运行）
anappt interactive
```

交互模式即**对话式 TUI**（textual 全屏界面，LLM 流式输出 + 思考滚动条）：输入自由文本即进入与 LLM 的多轮对话，由对话驱动阶段产出。元命令统一以 `/` 开头（大小写不敏感）：

| 元命令 | 作用 |
|--------|------|
| `/confirm` | 确认当前阶段产出，推进到下一阶段 |
| `/exit` | 退出对话式 TUI |
| `/status` | 查看各阶段状态 |
| `/memory` | 查看跨阶段共享记忆 `.anappt/memory.md` |
| `/help` | 显示元命令帮助 |
| `/ppt <需求>` | 跳过 S1–S5 前置阶段，直达生成 PPT |

详见 [交互模式指南](tui-usage.md)。

## 会话日志

每个阶段在 `.anappt/session_history/` 下生成独立的会话日志，文件名为 `YYYY-MM-DD_<stage>.md`（UTC 日期，如 `2024-12-01_S1.md`、`2024-12-01_S4.md`）。日志结构为：

- `## 核心摘要`：由 LLM 生成的本次对话重点摘要（1-3 句）
- `### 对话记录`：按时间戳记录的 Agent/用户对话内容

便于回溯与审计。
