# AnaPPTAgent

> Analysis report writing and PPT auto-generation agent tool — from raw data to slide deck, fully automated.

**[English](https://github.com/SidneyLYZhang/AnaPPTAgent/blob/HEAD/README_en.md)** | **[中文](https://github.com/SidneyLYZhang/AnaPPTAgent/blob/HEAD/README_zh.md)**

---

## Six-Stage Pipeline

| Stage | Name                      | Model Role | Description                                         |
|-------|---------------------------|------------|-----------------------------------------------------|
| S1    | Topic & Goal Definition   | reasoning  | Analyzes report.yaml, refines topic and objectives  |
| S2    | Data Requirement Analysis | reasoning  | Determines what data is needed, expected schemas    |
| S3    | Data Loading & Validation | —          | Loads data files, generates data profile summary     |
| S4    | Data Analysis             | analysis   | Agent loop with code execution, web search tools    |
| S5    | Report Generation         | writing    | Transforms analysis into polished report            |
| S6    | PPT Generation            | writing    | Converts report to HTML slide presentation          |

Each stage pauses for user review (confirm or revise) before proceeding.

## Quick Install

### Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- (Optional) [Node.js](https://nodejs.org/) >= 20 — for PPTX export

### Install

```bash
git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
cd AnaPPTAgent
uv sync --extra dev
uv pip install -e .
```

### Windows Automated Setup

```powershell
.\scripts\setup-windows.ps1
```

### 环境准备(首次使用)

克隆本仓库到本地后,在开始使用前请先运行以下命令完成运行环境检查与 dashi-ppt-skill 安装:

```bash
anappt setup
```

该命令会依次:
1. 检查 Node.js >= 20 与 npm 是否已安装
2. 警告(非阻塞)若未检测到 Chrome/Chromium/Edge(PPTX/PDF 导出需要)
3. 通过 `npx dashi-ppt-skill@latest --dir ~/.anappt/skills/` 安装 dashi-ppt-skill 到机器级目录
4. 将 skill 路径持久化到 `~/.anappt/config.yaml`

**国内网络**:可加 `--registry` 参数使用镜像:

```bash
anappt setup --registry https://registry.npmmirror.com
```

**自定义 skill 安装目录**:

```bash
anappt setup --dir /path/to/skills
```

### Quick Start

```bash
anappt config set          # Configure LLM models
anappt new my_report       # Create a new project
cd my_report
# Edit report.yaml, place data files in data/
anappt run                 # Run the pipeline
```

## Documentation

| Document | Description |
|----------|-------------|
| [CLI Usage Guide](docs/cli-usage.md) | All CLI commands, config, and environment variables |
| [Interactive TUI Guide](docs/tui-usage.md) | Interactive mode commands and workflow |
| [Report Workflow](docs/report-workflow.md) | Stages S1-S5 detailed workflow |
| [PPT Workflow](docs/ppt-workflow.md) | Stage S6 PPT generation workflow |

## License

MIT
