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
| `anappt new <name> [--no-skill] [--registry <url>]` | Create a new analysis project |
| `anappt init <name> [--no-skill] [--registry <url>]` | Create a new analysis project (alias for `new`) |
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
# Create a new project named my_report
anappt new my_report

# Use the init alias
anappt init my_report

# Skip dashi-ppt-skill download
anappt new my_report --no-skill

# Specify an npm registry (to speed up skill download)
anappt new my_report --registry https://registry.npmmirror.com
```

This creates the following directory structure:

```
my_report/
├── report.yaml
├── .gitignore
├── data/
│   └── README.md
├── output/
│   ├── report.md               # S5 output: analysis report
│   ├── images/
│   └── ppt/
│       ├── goal.json           # S6 intermediate artifact: slide structure built by LLM
│       ├── presentation.pptx   # S6 optional artifact: PPTX (when formats contains pptx)
│       └── ppt/
│           └── index.html      # S6 output: HTML slides (full path output/ppt/ppt/index.html)
└── .anappt/
    ├── state.yaml
    ├── s1_topic.md
    ├── s2_data_requirement.md
    ├── s3_data_profile.md
    ├── s4_analysis_report.md
    ├── data_info.json          # S4 artifact: data structure info
    ├── s5_report.md
    └── session_history/
        └── S1_session.md       # Session log named by stage ID
```

### Run the Pipeline

```bash
# Run from within the project directory
cd my_report
anappt run
```

The pipeline executes S1 through S6 sequentially, pausing after each stage for user review.

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
# Start interactive mode (must be run from a project directory)
anappt interactive
```

Interactive mode provides a command loop supporting `confirm`, `status`, `config`, `reset`, `help`, `exit`, and more. See the [Interactive TUI Guide](tui-usage.md) for details.

## Session Logs

Each stage produces an independent session log under `.anappt/session_history/`, named `{stage_id}_session.md` (e.g., `S1_session.md`, `S4_session.md`). The log records the conversation between the LLM and the user during that stage, useful for review and auditing.
