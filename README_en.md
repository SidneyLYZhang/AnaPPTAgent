# AnaPPTAgent

Analysis report writing and PPT auto-generation agent tool — from raw data to slide deck, fully automated.

[中文文档](https://github.com/SidneyLYZhang/AnaPPTAgent/blob/HEAD/README_zh.md) | **English**

---

## Overview

AnaPPTAgent is a CLI-based agent that transforms raw data files into polished analysis reports and HTML slide presentations. It orchestrates a six-stage gated pipeline where an LLM reasons about your topic, analyzes your data, writes a report, and generates a presentation — all with human review at each gate.

## Requirements

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- (Optional) [Node.js](https://nodejs.org/) >= 20, npm, Chrome/Chromium/Edge — for PPTX export via dashi-ppt-skill

## Installation

```bash
git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
cd AnaPPTAgent
uv sync --extra dev
```

This installs all runtime and development dependencies.

### Windows Quick Setup

Run the provided setup script to install prerequisites via winget:

```powershell
.\scripts\setup-windows.ps1
```

## Configuration

### Global Model Config

Create `~/.anappt/models.yaml`:

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

Or use the interactive configurator:

```bash
anappt config set
```

View current configuration:

```bash
anappt config show
```

Three model roles are supported:

| Role       | Stages | Purpose                          |
|------------|--------|----------------------------------|
| reasoning  | S1-S2  | Topic definition, data analysis |
| analysis   | S4     | Data analysis with tool-calling   |
| writing    | S5-S6  | Report writing, PPT generation    |

Any litellm-supported provider works (OpenAI, Anthropic, DeepSeek, Azure, etc.).

### Environment Variables

```bash
# LLM API keys (use ${VAR} syntax in models.yaml)
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export DEEPSEEK_API_KEY="..."

# Web search backends (optional, DuckDuckGo is the default)
export ANYSEARCH_API_KEY="..."     # AnySearch backend
export ZAI_API_KEY="..."            # z.ai (Zhipu) backend
export WEB_SEARCH_BACKEND="anysearch"  # or "zai", "duckduckgo"

# Web fetch (optional, used by S4 analysis agent)
export JINA_API_KEY="..."          # Jina Reader API for web page reading

# System proxy (optional)
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
export ALL_PROXY="socks5://127.0.0.1:7890"
```

## Quick Start

```bash
# 1. Create a new project
anappt new my_report

# 2. Navigate to project directory
cd my_report

# 3. Edit report.yaml — define your topic, audience, objectives
#    (Open report.yaml in your editor)

# 4. Place data files in data/
#    Supported formats: CSV, Excel, SQLite, DuckDB, Parquet
cp ~/sales_data.csv data/

# 5. Run the pipeline
anappt run

# 6. Review each stage output, type 'confirm' to proceed
#    Or type revision feedback to re-run the stage

# 7. After S5, review the generated report at output/report.md
# 8. After S6, open the presentation at output/ppt/presentation.html
```

## Command Reference

| Command                        | Description                                      |
|--------------------------------|--------------------------------------------------|
| `anappt new <name>`            | Create a new project directory                    |
| `anappt run`                   | Start or resume the pipeline                      |
| `anappt resume`                | Resume the pipeline from current state             |
| `anappt status`                | Show all stage statuses                           |
| `anappt config show`           | Display current model configuration                |
| `anappt config set`            | Interactively configure models                    |
| `anappt interactive`           | Start interactive mode with command loop          |

## Project Structure

### Tool Structure (this repository)

```
AnaPPTAgent/
├── src/anappt/
│   ├── __init__.py
│   ├── i18n.py                 # Internationalization (zh/en)
│   ├── types.py                # PipelineContext, StageOutput, UI Protocol
│   ├── stage_base.py           # Abstract stage base class
│   ├── orchestrator.py         # Pipeline orchestrator
│   ├── project.py              # Project initialization
│   ├── cli.py                  # CLI entry point + InteractiveUI
│   ├── io/
│   │   ├── config.py           # ReportConfig, ModelsConfig
│   │   ├── state.py             # StateManager, StageStatus
│   │   ├── data_loader.py      # Multi-format data loading
│   │   ├── git_auto.py         # Git auto-commit
│   │   └── session.py          # SessionLogger
│   ├── llm/
│   │   ├── models.py           # ModelRole type
│   │   └── provider.py         # AnaPPTLLM (litellm wrapper)
│   ├── tools/
│   │   ├── web_search.py       # Web search (3 backends)
│   │   ├── web_fetch.py        # Jina Reader web fetch
│   │   ├── code_exec.py        # Sandboxed Python execution
│   │   └── agent_loop.py       # Tool-calling agent loop
│   ├── bridge/
│   │   └── dashi_ppt.py        # HTML presentation generator
│   ├── stages/
│   │   ├── s1_topic.py         # Topic & goal definition
│   │   ├── s2_data_req.py      # Data requirement analysis
│   │   ├── s3_data_load.py     # Data loading & validation
│   │   ├── s4_analysis.py      # Data analysis (agent loop)
│   │   ├── s5_report.py        # Report generation
│   │   └── s6_ppt.py           # PPT generation
│   └── locales/
│       ├── zh.json
│       └── en.json
├── templates/project/          # Project scaffolding templates
├── tests/                      # Test suite (441 tests)
├── scripts/                    # Setup scripts
├── docs/                       # Documentation
├── pyproject.toml
└── ruff.toml
```

### Analysis Project Structure (created by `anappt new`)

```
my_report/
├── report.yaml                 # Report configuration (topic, audience, etc.)
├── .gitignore
├── data/                       # Place your data files here
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
    └── session_history/        # Conversation logs per stage
```

## dashi-ppt-skill Dependency

The PPT generation (S6) produces a self-contained HTML presentation. For PPTX export:

- **Node.js** >= 20 and **npm** must be installed
- **Chrome/Chromium/Edge** browser is required for PPTX rendering
- Install the dashi-ppt-skill globally:

```bash
npm install -g dashi-ppt-skill
```

If Node.js is not available, AnaPPTAgent falls back to HTML-only output which can be opened in any browser and printed to PDF.

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

## Internationalization

AnaPPTAgent supports Chinese (default) and English. Set the `LANG` environment variable:

```bash
# English
export LANG=en_US.UTF-8

# Chinese (default)
export LANG=zh_CN.UTF-8
```

## Documentation

- [CLI Usage Guide](docs/cli-usage.md)
- [Interactive TUI Guide](docs/tui-usage.md)
- [Report Generation Workflow](docs/report-workflow.md)
- [PPT Generation Workflow](docs/ppt-workflow.md)

## License

MIT
