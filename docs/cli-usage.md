# CLI 使用指南 / CLI Usage Guide

## 中文

### 前置条件

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) 包管理器
- 全局模型配置文件 `~/.anappt/models.yaml`

### 命令一览

AnaPPTAgent 的 CLI 入口为 `anappt`，支持以下子命令：

| 命令 | 说明 |
|------|------|
| `anappt` | 无参数时显示帮助信息 |
| `anappt new <name>` | 创建新分析项目 |
| `anappt init <name>` | 创建新分析项目（`new` 的别名） |
| `anappt run` | 启动或恢复流水线 |
| `anappt resume` | 从当前状态恢复流水线 |
| `anappt status` | 显示所有阶段状态 |
| `anappt config show` | 显示当前模型配置 |
| `anappt config set` | 交互式配置模型 |
| `anappt interactive` | 启动交互模式 |

### 全局配置文件

全局模型配置文件位于 `~/.anappt/models.yaml`，定义三种模型角色：

```yaml
reasoning:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}

analysis:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}

writing:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}
```

| 角色 | 阶段 | 用途 |
|------|------|------|
| reasoning | S1-S2 | 选题定义、数据需求分析 |
| analysis | S4 | 数据分析（工具调用） |
| writing | S5-S6 | 报告撰写、PPT 生成 |

支持所有 litellm 兼容的 provider（OpenAI、Anthropic、DeepSeek、Azure 等）。

### 项目配置文件

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

#### 字段详解

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

### 环境变量

| 环境变量 | 说明 |
|---------|------|
| `OPENAI_API_KEY` | OpenAI API 密钥 |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `ANYSEARCH_API_KEY` | AnySearch Web 搜索后端密钥 |
| `ZAI_API_KEY` | z.ai（智谱）Web 搜索后端密钥 |
| `WEB_SEARCH_BACKEND` | 显式指定搜索后端：`anysearch`、`zai`、`duckduckgo` |
| `JINA_API_KEY` | Jina Reader API 密钥，用于网页读取 |
| `HTTP_PROXY` | HTTP 代理地址 |
| `HTTPS_PROXY` | HTTPS 代理地址 |
| `ALL_PROXY` | 全局代理地址（支持 socks5） |
| `LANG` | 语言选择：`zh_CN.UTF-8`（默认）或 `en_US.UTF-8` |

### 命令示例

#### 创建新项目

```bash
# 创建名为 my_report 的新项目
anappt new my_report

# 使用 init 别名
anappt init my_report
```

创建后生成如下目录结构：

```
my_report/
├── report.yaml                 # 报告配置
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
    └── session_history/        # 会话日志
```

#### 运行流水线

```bash
# 在项目目录中运行
cd my_report
anappt run
```

流水线会依次执行 S1 到 S6，每个阶段完成后暂停等待用户确认。

#### 恢复流水线

```bash
# 从上次中断处恢复
anappt resume
```

#### 查看状态

```bash
# 显示所有阶段的状态
anappt status
```

输出示例：

```
Stage | Name                      | Status
------+---------------------------+---------
S1    | Topic & Goal Definition   | confirmed
S2    | Data Requirement Analysis | confirmed
S3    | Data Loading & Validation | confirmed
S4    | Data Analysis             | running
S5    | Report Generation         | pending
S6    | PPT Generation            | pending
```

#### 配置模型

```bash
# 显示当前模型配置
anappt config show

# 交互式配置模型
anappt config set
```

`config set` 会引导用户逐一配置 reasoning、analysis、writing 三种模型角色的 provider、model 和 api_key。

#### 交互模式

```bash
# 启动交互模式（必须在项目目录中运行）
anappt interactive
```

交互模式提供命令循环，支持 `confirm`、`status`、`config`、`reset`、`help`、`exit` 等命令。详见 [交互模式指南](tui-usage.md)。

---

## English

### Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- Global model config file at `~/.anappt/models.yaml`

### Command Reference

The CLI entry point is `anappt`, supporting the following subcommands:

| Command | Description |
|---------|-------------|
| `anappt` | Shows usage help when called with no arguments |
| `anappt new <name>` | Create a new analysis project |
| `anappt init <name>` | Create a new analysis project (alias for `new`) |
| `anappt run` | Start or resume the pipeline |
| `anappt resume` | Resume the pipeline from current state |
| `anappt status` | Show all stage statuses |
| `anappt config show` | Display current model configuration |
| `anappt config set` | Interactively configure models |
| `anappt interactive` | Start interactive mode |

### Global Config File

The global model config file is located at `~/.anappt/models.yaml` and defines three model roles:

```yaml
reasoning:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}

analysis:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}

writing:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}
```

| Role | Stages | Purpose |
|------|--------|---------|
| reasoning | S1-S2 | Topic definition, data requirement analysis |
| analysis | S4 | Data analysis with tool-calling |
| writing | S5-S6 | Report writing, PPT generation |

Any litellm-supported provider works (OpenAI, Anthropic, DeepSeek, Azure, etc.).

### Project Config File

Each analysis project has a `report.yaml` configuration file in the project root directory. Field descriptions:

```yaml
project:
  name: ""           # project name
  type: "one_time"   # one_time | monthly | quarterly
  created: ""        # creation date (auto-generated)

report:
  topic: ""          # analysis topic
  motivation: ""     # why this analysis matters
  audience: []       # target audience list
  objectives: []     # analysis objectives
  success_criteria: []  # success criteria

delivery:
  ppt_pages: "15-20"       # desired PPT page count
  formats: ["pptx", "html"]  # output formats
  theme_preference: null   # PPT theme, null = choose in S6
```

#### Field Details

| Field | Type | Description |
|-------|------|-------------|
| `project.name` | string | Project name for identification |
| `project.type` | string | Project type: `one_time`, `monthly`, or `quarterly` |
| `project.created` | string | Creation date, auto-filled by `anappt new` |
| `report.topic` | string | Analysis topic, describes what to analyze |
| `report.motivation` | string | Motivation and background for the analysis |
| `report.audience` | list | Target audience, e.g., management, technical team |
| `report.objectives` | list | List of analysis objectives |
| `report.success_criteria` | list | Success criteria for measuring analysis quality |
| `delivery.ppt_pages` | string | Desired PPT page count range, e.g., `"15-20"` |
| `delivery.formats` | list | Output format list, supports `pptx` and `html` |
| `delivery.theme_preference` | string/null | PPT theme, set to `null` to choose interactively in S6 |

### Environment Variables

| Environment Variable | Description |
|---------------------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `ANYSEARCH_API_KEY` | AnySearch web search backend key |
| `ZAI_API_KEY` | z.ai (Zhipu) web search backend key |
| `WEB_SEARCH_BACKEND` | Explicit backend selection: `anysearch`, `zai`, or `duckduckgo` |
| `JINA_API_KEY` | Jina Reader API key for web page reading |
| `HTTP_PROXY` | HTTP proxy address |
| `HTTPS_PROXY` | HTTPS proxy address |
| `ALL_PROXY` | Global proxy address (supports socks5) |
| `LANG` | Language selection: `zh_CN.UTF-8` (default) or `en_US.UTF-8` |

### Command Examples

#### Create a New Project

```bash
# Create a new project named my_report
anappt new my_report

# Use the init alias
anappt init my_report
```

This creates the following directory structure:

```
my_report/
├── report.yaml                 # Report configuration
├── .gitignore
├── data/                       # Data files directory
│   └── README.md
├── output/                     # Generated artifacts
│   ├── report.md               # S5 output: analysis report
│   ├── images/                 # Charts and images
│   └── ppt/
│       └── presentation.html   # S6 output: HTML slides
└── .anappt/
    ├── state.yaml              # Pipeline state
    ├── s1_topic.md             # S1 artifact
    ├── s2_data_requirement.md  # S2 artifact
    ├── s3_data_profile.md      # S3 artifact
    ├── s4_analysis_report.md   # S4 artifact
    ├── s5_report.md            # S5 artifact copy
    └── session_history/        # Session logs
```

#### Run the Pipeline

```bash
# Run from within the project directory
cd my_report
anappt run
```

The pipeline executes S1 through S6 sequentially, pausing after each stage for user review.

#### Resume the Pipeline

```bash
# Resume from where it was interrupted
anappt resume
```

#### Check Status

```bash
# Show all stage statuses
anappt status
```

Example output:

```
Stage | Name                      | Status
------+---------------------------+---------
S1    | Topic & Goal Definition   | confirmed
S2    | Data Requirement Analysis | confirmed
S3    | Data Loading & Validation | confirmed
S4    | Data Analysis             | running
S5    | Report Generation         | pending
S6    | PPT Generation            | pending
```

#### Configure Models

```bash
# Display current model configuration
anappt config show

# Interactively configure models
anappt config set
```

`config set` guides the user through configuring the provider, model, and api_key for each of the three model roles: reasoning, analysis, and writing.

#### Interactive Mode

```bash
# Start interactive mode (must be run from a project directory)
anappt interactive
```

Interactive mode provides a command loop supporting `confirm`, `status`, `config`, `reset`, `help`, `exit`, and more. See the [Interactive TUI Guide](tui-usage.md) for details.
