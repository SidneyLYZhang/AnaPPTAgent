# CLI Usage Guide

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- Global model config file at `~/.anappt/models.yaml`

## Command Reference

The CLI entry point is `anappt`, supporting the following subcommands:

| Command | Description |
|---------|-------------|
| `anappt` | Shows usage help when called with no arguments |
| `anappt new [<name>] [--no-skill] [--registry <url>]` | Create a new analysis project; without `<name>`, initialize the current directory in place; with `<name>`, create a same-named subdirectory under the current directory |
| `anappt init [<name>] [--no-skill] [--registry <url>]` | Create a new analysis project (alias for `new`); also supports in-place initialization when no name is given |
| `anappt run` | Start or resume the pipeline |
| `anappt resume` | Resume the pipeline from current state |
| `anappt status` | Show all stage statuses |
| `anappt config show` | Display the full effective configuration (incl. thinking, web search/fetch, API key masked, sources annotated) |
| `anappt config set` | Interactively configure three model roles (incl. thinking) and web_search/web_fetch |
| `anappt interactive` | Start interactive mode |
| `anappt setup [--dir <path>] [--registry <url>]` | Check environment and install/update dashi-ppt-skill |

## Global Config File

!!! info "Full configuration guide"
    See [Configuration Guide](configuration.en.md).

The global model config file is located at `~/.anappt/models.yaml` (**all configuration lives here; project-level overrides are no longer supported**) and defines three model roles plus optional web capabilities:

```yaml
reasoning:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}
  # thinking omitted → use the model's maximum thinking effort

analysis:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: ${ANTHROPIC_API_KEY}
  thinking: FALSE              # explicitly disable thinking

writing:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}
  # thinking omitted → use the model's maximum thinking effort

# Web search (optional section; defaults to DuckDuckGo, no key required)
web_search:
  backend: anysearch                       # optional: duckduckgo | anysearch | zai
  anysearch_api_key: ${ANYSEARCH_API_KEY}  # optional; env var takes precedence over yaml
  zai_api_key: ${ZAI_API_KEY}              # optional; env var takes precedence over yaml

# Web fetch (optional section; disabled by default)
web_fetch:
  jina_api_key: ${JINA_API_KEY}            # optional; env var takes precedence over yaml
```

**Field notes**:

- `thinking` (optional): controls the reasoning effort for that role when calling the LLM.
  - Omitted → use the model's maximum thinking effort (for known providers an explicit "max" param is sent, e.g. OpenAI o-series `reasoning_effort="high"`).
  - String `FALSE` (case-insensitive; also accepts `False`/`false`/`OFF`/`off`) → disable thinking.
  - `low`/`medium`/`high` → call with the specified effort (e.g. OpenAI maps to `reasoning_effort`).
  - Integer N → passed as `budget_tokens` to providers that support it (e.g. Anthropic).
- `web_search` / `web_fetch` are optional sections; when omitted, web search defaults to DuckDuckGo (no key) and web fetch is disabled.
- **Environment variables take precedence over the corresponding fields in models.yaml**: when both an environment variable and a yaml field configure the same item, the environment variable wins.

| Role | Stages | Purpose |
|------|--------|---------|
| reasoning | S1-S2 | Topic definition, data requirement analysis |
| analysis | S4 | Data analysis with tool-calling |
| writing | S5-S6 | Report writing, PPT generation |

Any litellm-supported provider works (OpenAI, Anthropic, DeepSeek, Azure, etc.).

## Project Config File

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

### Field Details

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

!!! note "Generation and override of report.yaml"
    The `report.yaml` copied by `anappt new`/`init` is only a **placeholder template**. Once the pipeline starts, the S1 stage generates or refines `report.yaml` through conversation with the LLM (written back to the project root via the `write_artifact` tool), overwriting the placeholder fields. Template values are therefore for initial reference only; the effective content is whatever S1 produces.

## Environment Variables

| Environment Variable | Description |
|---------------------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `ANYSEARCH_API_KEY` | AnySearch web search backend key. **Takes precedence over `web_search.anysearch_api_key` in models.yaml**; when neither is set, anappt falls back to DuckDuckGo |
| `ZAI_API_KEY` | z.ai (Zhipu) web search backend key. **Takes precedence over `web_search.zai_api_key` in models.yaml** |
| `WEB_SEARCH_BACKEND` | Explicitly selects the search backend, one of `duckduckgo` / `anysearch` / `zai`. **Takes precedence over `web_search.backend` in models.yaml**; when unset, the backend is auto-selected based on available keys; when no key is present, DuckDuckGo is always used |
| `JINA_API_KEY` | Jina Reader API key for web page reading. **Takes precedence over `web_fetch.jina_api_key` in models.yaml**; when neither is set, web fetch is disabled |
| `HTTP_PROXY` | HTTP proxy address |
| `HTTPS_PROXY` | HTTPS proxy address |
| `ALL_PROXY` | Global proxy address (supports socks5) |
| `LANG` | Language selection: `zh_CN.UTF-8` (default) or `en_US.UTF-8` |

> **Precedence note**: For web search and web fetch, anappt follows a uniform **environment variable > models.yaml > default** precedence. When an environment variable is not set, anappt falls back to models.yaml; when neither is configured, the defaults apply (DuckDuckGo search / web fetch disabled).

## Command Examples

### Create a New Project

```bash
# Create a new project named my_report (creates a my_report/ subdirectory under the current directory)
anappt new my_report

# Use the init alias
anappt init my_report

# Without a name: initialize the current directory in place (no subdirectory created)
anappt init

# Skip dashi-ppt-skill download
anappt new my_report --no-skill

# Specify an npm registry (to speed up skill download)
anappt new my_report --registry https://registry.npmmirror.com
```

This creates the following directory structure:

```
my_report/
├── report.yaml                  # Project config (placeholder template; overwritten by S1)
├── .gitignore
├── data/
│   └── README.md
├── output/
│   ├── final_report.md          # S5 output: analysis report
│   ├── images/
│   └── ppt/
│       ├── goal.json            # S6 intermediate artifact: slide structure built by LLM
│       ├── presentation.pptx    # S6 optional artifact: PPTX (when formats contains pptx)
│       └── presentation.html    # S6 output: HTML slides
└── .anappt/
    ├── state.yaml               # Project init marker
    ├── memory.md                # Cross-stage shared memory (LLM-maintained)
    ├── s1_topic.md
    ├── s2_data_requirement.md
    ├── s3_data_profile.md
    ├── s4_analysis_report.md
    └── session_history/
        └── 2024-12-01_S1.md     # Session log named "date_stage"
```

### Run the Pipeline

```bash
# Run from within the project directory
cd my_report
anappt run
```

This enters a **conversational TUI** where multi-turn LLM conversations drive each stage's output (topic, data requirements, analysis, report, PPT, etc.). After each stage completes, use the `/confirm` meta-command to advance to the next stage; you may enter free text at any time to converse with the LLM, request changes, or add details.

### Resume the Pipeline

```bash
# Resume from where it was interrupted
anappt resume
```

### Check Status

```bash
# Show all stage statuses
anappt status
```

Example output:

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

Status values: `pending` (not started), `in_progress` (running), `awaiting_review` (awaiting user confirmation), `completed` (done).

### Configure Models

```bash
# Display current model configuration
anappt config show

# Interactively configure models
anappt config set
```

`config show` prints the current **effective configuration** (the merged result of env > yaml > defaults), including the three roles (with the `thinking` field), the `web_search` section (effective backend and whether each key is configured), and the `web_fetch` section (whether `jina_api_key` is configured). All `api_key` / `*_api_key` fields are masked (`${VAR}` literals are shown as-is, actual values are shown as `****<last 4>`, empty values as `<unset>`), and each field is annotated with its source (`(env)` / `(yaml)` / `(default)`).

`config set` guides the user through configuring the provider, model, api_base (optional), api_key, and `thinking` (optional; press Enter to skip and keep the default maximum thinking effort) for each of the three model roles: reasoning, analysis, and writing. After the three roles are configured, it asks whether to configure the `web_search` and `web_fetch` sections (all can be skipped to keep the defaults). The result is written to `~/.anappt/models.yaml` (**no** `models.yaml` is ever created in the project directory).

### Install dashi-ppt-skill

```bash
# Check the environment and install/update dashi-ppt-skill
anappt setup

# Specify the skill install parent directory
anappt setup --dir /path/to/skills

# Specify an npm registry
anappt setup --registry https://registry.npmmirror.com
```

`anappt setup` checks Node.js ≥ 20, npm, and Chrome (optional), then installs the skill to `~/.anappt/skills/dashi-ppt/` via `npx dashi-ppt-skill@latest --dir <path>`.

### Interactive Mode

```bash
# Start the conversational TUI (must be run from a project directory)
anappt interactive
```

Interactive mode is the **conversational TUI** (a full-screen textual interface with streaming LLM output + a live thinking bar): entering free text starts a multi-turn conversation with the LLM that drives each stage's output. Meta-commands all start with `/` (case-insensitive):

| Meta-command | Action |
|--------------|--------|
| `/confirm` | Confirm the current stage's output and advance to the next stage |
| `/exit` | Exit the conversational TUI |
| `/status` | Show the status of each stage |
| `/memory` | View the cross-stage shared memory `.anappt/memory.md` |
| `/help` | Show meta-command help |
| `/ppt <requirement>` | Skip the S1–S5 prep stages and generate a PPT directly |

See the [Interactive TUI Guide](tui-usage.md) for details.

## Session Logs

Each stage produces an independent session log under `.anappt/session_history/`, named `YYYY-MM-DD_<stage>.md` (UTC date, e.g., `2024-12-01_S1.md`, `2024-12-01_S4.md`). The log structure is:

- `## 核心摘要` (Core Summary): an LLM-generated summary of the key points of the conversation (1-3 sentences)
- `### 对话记录` (Dialog Record): the timestamped Agent/user conversation

Useful for review and auditing.
