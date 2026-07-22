# AnaPPTAgent

> Analysis report writing and PPT auto-generation agent tool — from raw data to slide deck, fully automated.

**[English](README_en.md)** | **[中文](README_zh.md)** | **[Docs](https://sidneylyzhang.github.io/AnaPPTAgent)**

---

## Quick Install

Run the appropriate one-liner for your platform. The script installs git, uv, (optionally) Node.js, clones the repo, and registers `anappt` as a global uv tool — all in five stages with verification at each step.

=== "Windows (PowerShell)"

    ```powershell
    Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/SidneyLYZhang/AnaPPTAgent/main/scripts/setup-windows.ps1 | Invoke-Expression
    ```

=== "Linux / macOS"

    ```bash
    curl -fsSL https://raw.githubusercontent.com/SidneyLYZhang/AnaPPTAgent/main/scripts/setup-unix.sh | bash
    ```

Prefer manual steps? See the [Installation Guide](https://sidneylyzhang.github.io/AnaPPTAgent/installation/).

## Quick Start

```bash
anappt config set          # Configure your LLM models (OpenAI, Anthropic, DeepSeek, etc.)
anappt new my_report       # Create a new project
cd my_report
# Place your data files in data/
anappt run                 # Start the six-stage pipeline
# In S1, chat with the LLM to define topic/audience/objectives — it generates report.yaml
```

Each stage pauses for your review (`confirm` to proceed, or type revision feedback). Final artifacts land in `output/final_report.md` (S5) and `output/ppt/presentation.html` (S6).

## Documentation

| Resource | Description |
|----------|-------------|
| [Documentation Site](https://sidneylyzhang.github.io/AnaPPTAgent) | Full docs site (installation, CLI, TUI, workflows) |
| [Installation Guide](https://sidneylyzhang.github.io/AnaPPTAgent/installation/) | Detailed install methods, troubleshooting, FAQ |
| [README (中文)](README_zh.md) | Detailed Chinese README |
| [README (English)](README_en.md) | Detailed English README |
| [CLI Usage](https://sidneylyzhang.github.io/AnaPPTAgent/cli-usage/) | All CLI commands and config |
| [Interactive TUI](https://sidneylyzhang.github.io/AnaPPTAgent/tui-usage/) | Interactive mode commands |
| [Report Workflow](https://sidneylyzhang.github.io/AnaPPTAgent/report-workflow/) | Stages S1-S5 detailed workflow |
| [PPT Workflow](https://sidneylyzhang.github.io/AnaPPTAgent/ppt-workflow/) | Stage S6 PPT generation |

## License

MIT
