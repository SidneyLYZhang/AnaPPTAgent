# AnaPPTAgent

分析报告撰写与 PPT 自动生成的智能体工具 —— 从原始数据到幻灯片，全流程自动化。

**中文** | [English](https://github.com/SidneyLYZhang/AnaPPTAgent/blob/HEAD/README_en.md)

---

## 简介

AnaPPTAgent 是一个基于命令行的智能体工具，将原始数据文件自动转化为精炼的分析报告和 HTML 幻灯片演示。它编排一个六阶段门控流水线，由 LLM 推理选题、分析数据、撰写报告并生成演示文稿——每个阶段都支持人工审核。

## 环境要求

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) 包管理器
- （可选）[Node.js](https://nodejs.org/) >= 20、npm、Chrome/Chromium/Edge — 用于 PPTX 导出

## 安装

AnaPPTAgent 提供三种安装方式，按推荐程度排列如下。

### 方式一：自动安装脚本（推荐）

一键脚本会自动安装依赖、克隆仓库并把 `anappt` 注册为全局 uv 工具。

=== "Windows"

    使用 PowerShell 执行：

    ```powershell
    Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/SidneyLYZhang/AnaPPTAgent/main/scripts/setup-windows.ps1 | Invoke-Expression
    ```

=== "Linux / macOS"

    使用 bash 执行：

    ```bash
    curl -fsSL https://raw.githubusercontent.com/SidneyLYZhang/AnaPPTAgent/main/scripts/setup-unix.sh | bash
    ```

也可以先克隆仓库，再运行仓库内的脚本：

=== "Windows"

    ```powershell
    git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
    cd AnaPPTAgent
    .\scripts\setup-windows.ps1
    ```

=== "Linux / macOS"

    ```bash
    git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
    cd AnaPPTAgent
    bash scripts/setup-unix.sh
    ```

脚本会依次执行 5 个阶段：git / uv / Node.js / clone / `uv tool install .`，每个阶段完成后都会运行验证测试确认产物可用。常用参数：

- `--skip-node`：跳过 Node.js 安装（不需要 PPTX 导出时使用）
- `--skip-clone`：跳过仓库克隆（已在仓库目录中运行时使用）
- `-r <repo-url>`：指定克隆用的仓库地址
- `-t <target-dir>`：指定克隆目标目录

### 方式二：手动安装

适合希望完全控制每一步、且只需要全局 `anappt` 命令的用户。

```bash
git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
cd AnaPPTAgent
uv tool install .
```

`uv tool install .` 会把 `anappt` 注册为全局 uv 工具，使其在 shell 中直接可用（无需 `uv run` 前缀）。如需开发依赖（pytest、ruff），单独运行 `uv sync --extra dev`。

### 方式三：开发模式

适合需要修改源码、运行测试或贡献代码的开发者。

```bash
git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
cd AnaPPTAgent
uv sync --extra dev
```

开发模式下通过 `uv run` 调用工具：

```bash
uv run anappt --help        # 查看帮助
uv run pytest               # 运行测试套件
uv run ruff check src tests # lint 检查
```

## 配置

### 全局模型配置

创建 `~/.anappt/models.yaml`（**所有配置集中在此文件,不再支持项目级覆盖**）：

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
  - 字段缺省 → 使用模型最大思考强度（对已知 provider 主动传"最大"参数,如 OpenAI o-series 的 `reasoning_effort="high"`)
  - 字符串 `FALSE`（大小写不敏感,也接受 `False`/`false`/`OFF`/`off`）→ 关闭思考
  - `low`/`medium`/`high` → 按指定强度调用（如 OpenAI 映射为 `reasoning_effort`）
  - 整数 N → 作为 `budget_tokens` 传递给支持的 provider（如 Anthropic）
- `web_search` / `web_fetch` 为可选段,缺省时：Web 搜索使用 DuckDuckGo（无需 key）,Web 读取禁用。
- **环境变量优先于 models.yaml 中的对应字段**：当环境变量与 yaml 同时配置同一项时,以环境变量的值为准。

或使用交互式配置器：

```bash
anappt config set
```

查看当前配置：

```bash
anappt config show
```

支持三种模型角色：

| 角色       | 阶段   | 用途                          |
|------------|--------|-------------------------------|
| reasoning  | S1-S2  | 选题定义、数据分析需求        |
| analysis   | S4     | 数据分析（工具调用）          |
| writing    | S5-S6  | 报告撰写、PPT 生成            |

支持所有 litellm 兼容的 provider（OpenAI、Anthropic、DeepSeek、Azure 等）。

### 环境变量

```bash
# LLM API Key（在 models.yaml 中使用 ${VAR} 语法引用）
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export DEEPSEEK_API_KEY="..."

# Web 搜索后端（可选，默认使用 DuckDuckGo）
# 注意:这些环境变量优先于 models.yaml 中的 web_search/web_fetch 配置;
# 未设置环境变量时回退到 models.yaml,两者均未配置时使用默认值
# (DuckDuckGo 搜索 / 禁用 web 读取)。
export ANYSEARCH_API_KEY="..."         # AnySearch 后端
export ZAI_API_KEY="..."               # z.ai（智谱）后端
export WEB_SEARCH_BACKEND="anysearch"  # 或 "zai"、"duckduckgo"

# Web 读取（可选，S4 分析智能体使用）
export JINA_API_KEY="..."              # Jina Reader API

# 系统代理（可选）
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
export ALL_PROXY="socks5://127.0.0.1:7890"
```

## 快速开始

```bash
# 1. 创建新项目
anappt new my_report

# 2. 进入项目目录
cd my_report

# 3. 编辑 report.yaml — 定义选题、受众、目标
#    （在编辑器中打开 report.yaml）

# 4. 将数据文件放入 data/
#    支持格式：CSV、Excel、SQLite、DuckDB、Parquet
cp ~/sales_data.csv data/

# 5. 运行流水线
anappt run

# 6. 审核每个阶段输出，输入 'confirm' 确认
#    或输入修改意见重新运行该阶段

# 7. S5 完成后，查看报告 output/report.md
# 8. S6 完成后，打开演示文稿 output/ppt/presentation.html
```

## 命令参考

| 命令                          | 说明                              |
|-------------------------------|-----------------------------------|
| `anappt init <name>`          | 创建新项目目录（`new` 的别名）    |
| `anappt new <name>`           | 创建新项目目录                    |
| `anappt run`                  | 启动或恢复流水线                  |
| `anappt resume`               | 从当前状态恢复流水线              |
| `anappt status`               | 查看所有阶段状态                  |
| `anappt config show`          | 显示当前完整有效配置（含 thinking、web 搜索/读取，API key 掩码，标注来源） |
| `anappt config set`           | 交互式配置三个模型角色（含 thinking）与 web_search/web_fetch 能力 |
| `anappt setup`                | 安装/初始化 dashi-ppt skill 等资源 |
| `anappt interactive`          | 启动交互模式                      |

## 项目结构

### 工具自身结构（本仓库）

```
AnaPPTAgent/
├── src/anappt/
│   ├── __init__.py
│   ├── i18n.py                 # 国际化（中文/英文）
│   ├── types.py                # PipelineContext, StageOutput, UI 协议
│   ├── stage_base.py           # 阶段抽象基类
│   ├── orchestrator.py         # 流水线编排器
│   ├── project.py              # 项目初始化
│   ├── cli.py                  # CLI 入口 + InteractiveUI
│   ├── io/                     # I/O 与持久化层
│   │   ├── config.py           # ReportConfig, ModelsConfig
│   │   ├── state.py            # StateManager, StageStatus
│   │   ├── data_loader.py      # 多格式数据加载
│   │   ├── git_auto.py         # Git 自动提交
│   │   ├── skill_manager.py    # dashi-ppt-skill 环境与安装管理
│   │   └── session.py          # SessionLogger
│   ├── llm/                    # LLM Provider 层
│   │   ├── models.py           # ModelRole 类型
│   │   └── provider.py         # AnaPPTLLM (litellm 封装)
│   ├── tools/                  # 工具层（搜索、读取、代码执行）
│   │   ├── web_search.py       # Web 搜索（3 种后端）
│   │   ├── web_fetch.py        # Jina Reader 网页读取
│   │   ├── code_exec.py        # 沙箱代码执行
│   │   └── agent_loop.py       # 工具调用智能体循环
│   ├── bridge/                 # dashi-ppt 桥接层
│   │   └── dashi_ppt.py        # HTML 演示文稿生成器
│   ├── stages/                 # 六阶段实现
│   │   ├── s1_topic.py         # 选题与目标定义
│   │   ├── s2_data_req.py      # 数据需求分析
│   │   ├── s3_data_load.py     # 数据加载与验证
│   │   ├── s4_analysis.py      # 数据分析（智能体循环）
│   │   ├── s5_report.py        # 报告生成
│   │   └── s6_ppt.py           # PPT 生成
│   └── locales/                # 中英文消息目录
│       ├── zh.json
│       └── en.json
├── templates/project/          # 项目脚手架模板
├── tests/                      # 测试套件（441 测试）
├── scripts/                    # 安装脚本
├── docs/                       # 文档
├── pyproject.toml
└── ruff.toml
```

### 分析项目结构（由 `anappt new` 创建）

```
my_report/
├── report.yaml                 # 报告配置（选题、受众等）
├── .gitignore
├── data/                       # 数据文件目录
│   └── README.md
├── output/                     # 生成产物
│   ├── report.md               # S5 输出：分析报告
│   ├── images/                 # 图表
│   └── ppt/
│       └── presentation.html   # S6 输出：HTML 幻灯片
└── .anappt/
    ├── state.yaml              # 流水线状态
    ├── s1_topic.md             # S1 产物
    ├── s2_data_requirement.md  # S2 产物
    ├── s3_data_profile.md      # S3 产物
    ├── s4_analysis_report.md   # S4 产物
    ├── s5_report.md            # S5 产物副本
    └── session_history/        # 各阶段会话日志
```

## dashi-ppt-skill 依赖说明

PPT 生成（S6）默认输出自包含的 HTML 演示文稿。如需 PPTX 导出：

- 需安装 **Node.js** >= 20 和 **npm**
- 需要 **Chrome/Chromium/Edge** 浏览器进行 PPTX 渲染
- 全局安装 dashi-ppt-skill：

```bash
npm install -g dashi-ppt-skill
```

若未安装 Node.js，AnaPPTAgent 将回退为仅输出 HTML 格式，可在任意浏览器中打开并打印为 PDF。

## 六阶段流程

| 阶段 | 名称             | 模型角色   | 说明                                      |
|------|------------------|------------|-------------------------------------------|
| S1   | 选题与目标定义    | reasoning  | 分析 report.yaml，精炼选题与目标          |
| S2   | 数据需求分析      | reasoning  | 确定所需数据，预期 schema                  |
| S3   | 数据加载与验证    | —          | 加载数据文件，生成数据档案摘要            |
| S4   | 数据分析          | analysis   | 智能体循环：代码执行、Web 搜索工具         |
| S5   | 报告生成          | writing    | 将分析结果转化为精炼报告                  |
| S6   | PPT 生成          | writing    | 将报告转为 HTML 幻灯片演示                |

每个阶段完成后暂停，等待用户确认（confirm）或修改意见后继续。

## 国际化

AnaPPTAgent 默认使用中文，也支持英文。通过 `LANG` 环境变量切换：

```bash
# 英文
export LANG=en_US.UTF-8

# 中文（默认）
export LANG=zh_CN.UTF-8
```

## 文档

完整文档站点：**https://sidneylyzhang.github.io/AnaPPTAgent**

| 文档 | 说明 |
|------|------|
| [安装指南](https://sidneylyzhang.github.io/AnaPPTAgent/installation/) | 详细安装方式、验证、升级卸载、常见问题 |
| [CLI 使用指南](https://sidneylyzhang.github.io/AnaPPTAgent/cli-usage/) | 所有 CLI 命令、配置与环境变量 |
| [交互式 TUI 指南](https://sidneylyzhang.github.io/AnaPPTAgent/tui-usage/) | 交互模式命令与工作流 |
| [报告生成流程](https://sidneylyzhang.github.io/AnaPPTAgent/report-workflow/) | S1-S5 阶段详细工作流 |
| [PPT 生成流程](https://sidneylyzhang.github.io/AnaPPTAgent/ppt-workflow/) | S6 阶段 PPT 生成工作流 |
| [中文 README](https://github.com/SidneyLYZhang/AnaPPTAgent/blob/HEAD/README_zh.md) | 本文件 |
| [English README](https://github.com/SidneyLYZhang/AnaPPTAgent/blob/HEAD/README_en.md) | 英文版 README |

本地文档源文件位于仓库 `docs/` 目录下（如 `docs/cli-usage.md`、`docs/tui-usage.md`、`docs/report-workflow.md`、`docs/ppt-workflow.md`、`docs/installation.md`）。

## 许可证

MIT
