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

```bash
git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
cd AnaPPTAgent
uv sync --extra dev
```

### Windows 快速安装

运行提供的安装脚本，通过 winget 自动安装依赖：

```powershell
.\scripts\setup-windows.ps1
```

## 配置

### 全局模型配置

创建 `~/.anappt/models.yaml`：

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
| `anappt new <name>`           | 创建新项目目录                    |
| `anappt run`                  | 启动或恢复流水线                  |
| `anappt resume`               | 从当前状态恢复流水线              |
| `anappt status`               | 查看所有阶段状态                  |
| `anappt config show`          | 显示当前模型配置                  |
| `anappt config set`           | 交互式配置模型                    |
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
│   │   ├── state.py             # StateManager, StageStatus
│   │   ├── data_loader.py      # 多格式数据加载
│   │   ├── git_auto.py         # Git 自动提交
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

- [CLI 使用指南](docs/cli-usage.md)
- [交互式 TUI 指南](docs/tui-usage.md)
- [报告生成流程](docs/report-workflow.md)
- [PPT 生成流程](docs/ppt-workflow.md)

## 许可证

MIT
