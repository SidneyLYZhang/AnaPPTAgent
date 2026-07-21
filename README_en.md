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

AnaPPTAgent can be installed in three ways depending on your use case. For most users, the **Automated Setup Script** is recommended.

### Method 1: Automated Setup Script (Recommended)

A one-liner downloads and runs the official setup script, which installs prerequisites, clones the repository, and registers the `anappt` command globally. The script runs five stages (git / uv / Node.js / clone / `uv tool install .`), each with a verification test that fails fast if a product is missing.

=== "Windows"

    ```powershell
    Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/SidneyLYZhang/AnaPPTAgent/main/scripts/setup-windows.ps1 | Invoke-Expression
    ```

=== "Linux / macOS"

    ```bash
    curl -fsSL https://raw.githubusercontent.com/SidneyLYZhang/AnaPPTAgent/main/scripts/setup-unix.sh | bash
    ```

You can also clone the repository first and run the script in-repo, which is useful for offline installs or when you want to inspect the script before executing it:

=== "Windows"

    ```powershell
    .\scripts\setup-windows.ps1
    ```

=== "Linux / macOS"

    ```bash
    bash scripts/setup-unix.sh
    ```

Common flags accepted by both scripts:

| Flag                  | Purpose                                                            |
|-----------------------|--------------------------------------------------------------------|
| `--skip-node`         | Skip Node.js installation (Stage 3) — use when Node is already present |
| `--skip-clone`        | Skip repository clone (Stage 4) — use when run from inside the repo   |
| `-r <repo-url>`       | Override the git remote URL                                         |
| `-t <target-dir>`     | Override the target parent directory for cloning                    |

### Method 2: Manual Install

If you prefer to control each step manually, clone the repository and install `anappt` as a global uv tool:

```bash
git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
cd AnaPPTAgent
uv tool install .
```

`uv tool install .` makes `anappt` globally available in your shell (no `uv run` prefix needed). For development dependencies (pytest, ruff), run `uv sync --extra dev` separately after this step.

### Method 3: Development Mode

For contributors who need the full dev environment (pytest, ruff, editable install), use `uv sync` with the `dev` extra instead of `uv tool install`:

```bash
git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
cd AnaPPTAgent
uv sync --extra dev
```

In dev mode the `anappt` entry point is not installed globally; invoke it through `uv run`:

```bash
uv run anappt --help          # Show CLI help
uv run pytest                 # Run the test suite
uv run ruff check src tests   # Lint the source tree
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
| `anappt init <name>`           | Alias of `anappt new` — create a new project      |
| `anappt run`                   | Start or resume the pipeline                      |
| `anappt resume`                | Resume the pipeline from current state             |
| `anappt status`                | Show all stage statuses                           |
| `anappt config show`           | Display current model configuration                |
| `anappt config set`            | Interactively configure models                    |
| `anappt interactive`           | Start interactive mode with command loop          |
| `anappt setup`                | Install/initialize dashi-ppt skill and other resources |

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
│   │   ├── state.py            # StateManager, StageStatus
│   │   ├── data_loader.py      # Multi-format data loading
│   │   ├── git_auto.py         # Git auto-commit
│   │   ├── skill_manager.py    # dashi-ppt-skill download & cache
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

Full documentation site: **https://sidneylyzhang.github.io/AnaPPTAgent**

| Document | Description |
|----------|-------------|
| [Installation Guide](https://sidneylyzhang.github.io/AnaPPTAgent/installation/) | Detailed install methods, verification, upgrade/uninstall, FAQ |
| [CLI Usage Guide](https://sidneylyzhang.github.io/AnaPPTAgent/cli-usage/) | All CLI commands, config, and environment variables |
| [Interactive TUI Guide](https://sidneylyzhang.github.io/AnaPPTAgent/tui-usage/) | Interactive mode commands and workflow |
| [Report Generation Workflow](https://sidneylyzhang.github.io/AnaPPTAgent/report-workflow/) | Stages S1-S5 detailed workflow |
| [PPT Generation Workflow](https://sidneylyzhang.github.io/AnaPPTAgent/ppt-workflow/) | Stage S6 PPT generation workflow |
| [Chinese README](https://github.com/SidneyLYZhang/AnaPPTAgent/blob/HEAD/README_zh.md) | Chinese version |
| [English README](https://github.com/SidneyLYZhang/AnaPPTAgent/blob/HEAD/README_en.md) | This file |

Local copies of the guides are also available under `docs/`:

- [Installation Guide](docs/installation.md)
- [CLI Usage Guide](docs/cli-usage.md)
- [Interactive TUI Guide](docs/tui-usage.md)
- [Report Generation Workflow](docs/report-workflow.md)
- [PPT Generation Workflow](docs/ppt-workflow.md)

## License

MIT
