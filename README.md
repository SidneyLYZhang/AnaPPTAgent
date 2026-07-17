# AnaPPTAgent

> Analysis report writing and PPT auto-generation agent tool — from raw data to slide deck, fully automated.

**[English](README_en.md)** | **[中文](README_zh.md)**

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
git clone <repo-url> AnaPPTAgent
cd AnaPPTAgent
uv sync --extra dev
uv pip install -e .
```

### Windows Automated Setup

```powershell
.\scripts\setup-windows.ps1
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
