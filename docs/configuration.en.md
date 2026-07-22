# Configuration Guide

All LLM and web-capability configuration for AnaPPTAgent lives in a single global file, `~/.anappt/models.yaml`. This page documents the file location, precedence, full schema, the `thinking` field semantics, web search/fetch configuration, environment variables, `${VAR}` expansion, the `config show` / `config set` commands, multi-provider examples, proxy settings, migration, and troubleshooting.

!!! info "Brief reference vs. full guide"
    The "Global Config File" section in the [CLI Usage Guide](cli-usage.en.md) provides a brief summary; this page is the complete reference. Read this page when configuring for the first time or troubleshooting.

## Configuration File Location

| Item | Value |
|------|-------|
| File path | `~/.anappt/models.yaml` (`~` is your home directory) |
| How to create | `anappt config set` (interactive) or create manually |
| When read | Every `anappt run` / `resume` / `config show` invocation |
| When written | After `anappt config set` completes the interactive flow |

!!! warning "Project-level models.yaml is no longer read"
    Earlier versions supported a project-level config at `<project>/.anappt/models.yaml`. **The current version no longer reads project-level models.yaml.** If the file is detected, a warning is printed:

    ```
    Project-level config <project>/.anappt/models.yaml is no longer read; please migrate its contents to ~/.anappt/models.yaml
    ```

    See [Migrating from project-level config](#migrating-from-project-level-config) for migration steps.

## Configuration Precedence

AnaPPTAgent applies a uniform precedence to every config item that can be overridden by an environment variable:

```
environment variable (env)  >  models.yaml (yaml)  >  default
```

- **Environment variables take precedence**: when both an environment variable and `models.yaml` configure the same item, **the environment variable wins**.
- **Default fallback**: when neither an environment variable nor `models.yaml` is set, a built-in default is used.
- **Scope**: web search backend and API keys, and the Jina web-fetch key all follow this precedence. LLM role `api_key` fields support `${VAR}` expansion (see below), so their "source" is indistinguishable after loading — `config show` therefore does not annotate LLM fields with a source.

!!! tip "Recommended practice"
    Reference environment variables in `models.yaml` via `${VAR}` (e.g. `api_key: ${OPENAI_API_KEY}`). This is both secure and lets you benefit from env-var precedence. See [${VAR} expansion](#var-expansion).

## Full Schema Reference

The complete structure of `models.yaml`:

```yaml
reasoning:
  provider: ""              # required, provider identifier
  model: ""                 # required, model name
  api_base: null            # optional, custom API endpoint
  api_key: null             # optional, API key (use ${VAR})
  thinking: null            # optional, thinking effort (see thinking field)

analysis:
  provider: ""
  model: ""
  api_base: null
  api_key: null
  thinking: null

writing:
  provider: ""
  model: ""
  api_base: null
  api_key: null
  thinking: null

web_search:                 # optional section, defaults to DuckDuckGo
  backend: null             # optional: duckduckgo | anysearch | zai
  anysearch_api_key: null   # optional, env var takes precedence
  zai_api_key: null         # optional, env var takes precedence

web_fetch:                  # optional section, disabled by default
  jina_api_key: null        # optional, env var takes precedence
```

### Field Reference

| Field | Type | Optional | Default | Description |
|-------|------|----------|---------|-------------|
| `*.provider` | string | required | `""` | Provider identifier, e.g. `openai`, `anthropic`, `deepseek`. Empty string is treated as OpenAI |
| `*.model` | string | required | `""` | Model name, e.g. `gpt-4o`, `claude-sonnet-4-20250514` |
| `*.api_base` | string \| null | optional | `null` | Custom API endpoint (for proxies or compatible APIs) |
| `*.api_key` | string \| null | optional | `null` | API key; using `${VAR}` to reference an env var is recommended |
| `*.thinking` | string \| int \| bool \| null | optional | `null` | Thinking effort; see [thinking field](#thinking-field) |
| `web_search.backend` | string \| null | optional | `null` (auto) | Search backend: `duckduckgo` / `anysearch` / `zai` |
| `web_search.anysearch_api_key` | string \| null | optional | `null` | AnySearch backend key; env var `ANYSEARCH_API_KEY` takes precedence |
| `web_search.zai_api_key` | string \| null | optional | `null` | z.ai backend key; env var `ZAI_API_KEY` takes precedence |
| `web_fetch.jina_api_key` | string \| null | optional | `null` | Jina Reader key; env var `JINA_API_KEY` takes precedence |

## LLM Model Roles

AnaPPTAgent's 6-stage pipeline (S1-S6) uses three model roles, each independently configurable:

| Role | Stages | Purpose |
|------|--------|---------|
| `reasoning` | S1-S2 | Topic definition, data-requirement analysis |
| `analysis` | S4 | Data analysis (tool-calling) |
| `writing` | S5-S6 | Report writing, PPT generation |

!!! note "S3 does not call the LLM"
    S3 (Data Loading & Validation) is purely local processing; it does not call the LLM and therefore uses no model role.

Any [LiteLLM](https://docs.litellm.ai/)-compatible provider works, including OpenAI, Anthropic, DeepSeek, Azure OpenAI, Tongyi Qianwen, Moonshot, and more. The `provider` value affects how the `thinking` field is mapped (see below).

## thinking field

The `thinking` field controls the **reasoning effort** when calling the LLM for that role. It is an optional, flexibly-typed field.

### Semantics Summary

| `thinking` value | Meaning | OpenAI behavior | Anthropic behavior | Other providers |
|------------------|---------|-----------------|--------------------|-----------------|
| omitted / `null` | Use the model's maximum thinking effort | sends `reasoning_effort: "high"` | sends nothing (uses default max) | sends nothing |
| `FALSE` / `OFF` (case-insensitive) | Disable thinking | sends `reasoning_effort: "minimal"` | sends nothing | sends nothing |
| `low` / `medium` / `high` | Specified effort | sends `reasoning_effort: <value>` | silently skipped | silently skipped |
| Integer N (e.g. `8000`) | Token budget | silently skipped | sends `thinking: {type: "enabled", budget_tokens: N}` | silently skipped |

!!! tip "Omitted means maximum"
    When the `thinking` field is omitted, AnaPPTAgent **proactively** sends a "max" parameter for known providers (e.g. `reasoning_effort: "high"` for OpenAI o-series) to ensure the default is maximum effort. For providers like Anthropic that already default to maximum thinking, nothing is sent so the model uses its default.

!!! note "Unsupported providers do not error"
    When `thinking` is set to `low`/`medium`/`high` or an integer but the provider does not support the corresponding parameter, AnaPPTAgent **silently skips** the mapping — no error is raised. The model runs with its default behavior.

### Provider Recognition Rules

The `thinking` mapping depends on matching the provider string (case-insensitive):

| Match | Condition | Examples |
|-------|-----------|----------|
| OpenAI | `provider` contains `openai`, or is empty `""` | `openai`; `azure` with OpenAI models usually matches too |
| Anthropic | `provider` contains `anthropic` or `claude` | `anthropic`, `claude` |
| Other | neither of the above | `deepseek`, `moonshot`, etc. → thinking mapping skipped |

### YAML Example

```yaml
reasoning:
  provider: openai
  model: o3-mini
  api_key: ${OPENAI_API_KEY}
  thinking: high              # explicit high effort

analysis:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: ${ANTHROPIC_API_KEY}
  thinking: FALSE             # disable thinking (speeds up S4)

writing:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}
  # thinking omitted → maximum effort
```

## Web Search Configuration

The `web_search` section controls the web-search capability used during S4 data analysis. AnaPPTAgent supports three search backends.

### Backend Selection Logic

The search backend is determined by the following precedence:

1. **Environment variable `WEB_SEARCH_BACKEND`** (if set to a valid value `duckduckgo` / `anysearch` / `zai`)
2. **`web_search.backend` in `models.yaml`**
3. **Auto-select based on available API keys**: when both AnySearch and z.ai keys are available, AnySearch is preferred; with only a z.ai key, z.ai is used; with no key, DuckDuckGo is used.

!!! warning "Explicit backend with missing key falls back"
    If you explicitly set `backend: anysearch` but no `ANYSEARCH_API_KEY` is configured (neither env nor yaml), a warning is printed and it **falls back to DuckDuckGo**. Same for `zai`.

### Three Backend Configurations

=== "DuckDuckGo (default, no key required)"

    Free, no API key needed, but may be rate-limited. Works with no configuration:

    ```yaml
    # Omit the web_search section entirely, or set:
    web_search:
      backend: duckduckgo
    ```

=== "AnySearch"

    Requires `ANYSEARCH_API_KEY` (env var takes precedence over yaml):

    ```yaml
    web_search:
      backend: anysearch
      anysearch_api_key: ${ANYSEARCH_API_KEY}
    ```

=== "z.ai (Zhipu)"

    Requires `ZAI_API_KEY` (env var takes precedence over yaml):

    ```yaml
    web_search:
      backend: zai
      zai_api_key: ${ZAI_API_KEY}
    ```

!!! tip "Auto-select mode"
    When `backend` is not set, AnaPPTAgent auto-selects based on configured keys. This is the easiest approach:

    ```yaml
    web_search:
      anysearch_api_key: ${ANYSEARCH_API_KEY}
      # backend omitted → detecting the anysearch key uses AnySearch
    ```

## Web Fetch Configuration

The `web_fetch` section controls the web-page reading capability during S4, using the [Jina Reader](https://r.jina.ai/) service to convert pages to Markdown.

- **Disabled by default**: when `web_fetch` is not configured or `jina_api_key` is unset, web fetch is off and S4 does not register the `fetch_url` tool.
- **Enabling**: set `jina_api_key`; env var `JINA_API_KEY` takes precedence over yaml.

```yaml
web_fetch:
  jina_api_key: ${JINA_API_KEY}
```

!!! note "Web fetch and web search are independent"
    Web search (DuckDuckGo/AnySearch/z.ai) and web fetch (Jina Reader) are two independent capabilities that can be enabled or disabled separately. For example, you can enable search without enabling fetch.

## Environment Variables Reference

| Environment variable | Description | Precedence over models.yaml |
|---------------------|-------------|-----------------------------|
| `OPENAI_API_KEY` | OpenAI API key | — (referenced via `${VAR}`) |
| `ANTHROPIC_API_KEY` | Anthropic API key | — (referenced via `${VAR}`) |
| `DEEPSEEK_API_KEY` | DeepSeek API key | — (referenced via `${VAR}`) |
| `ANYSEARCH_API_KEY` | AnySearch search backend key | ✅ overrides `web_search.anysearch_api_key` |
| `ZAI_API_KEY` | z.ai search backend key | ✅ overrides `web_search.zai_api_key` |
| `WEB_SEARCH_BACKEND` | Explicitly selects the search backend (`duckduckgo`/`anysearch`/`zai`) | ✅ overrides `web_search.backend` |
| `JINA_API_KEY` | Jina Reader web-fetch key | ✅ overrides `web_fetch.jina_api_key` |
| `HTTP_PROXY` | HTTP proxy address | — |
| `HTTPS_PROXY` | HTTPS proxy address | — |
| `ALL_PROXY` | Global proxy address (supports socks5) | — |
| `LANG` | Language selection: `zh_CN.UTF-8` (default) or `en_US.UTF-8` | — |

!!! note "Two kinds of environment variables"
    - **LLM API keys** (`OPENAI_API_KEY`, etc.): referenced in `models.yaml` via the `${VAR}` syntax and expanded at load time. They are not read directly by code; they take effect indirectly through `${VAR}`.
    - **Web config env vars** (`ANYSEARCH_API_KEY`, `ZAI_API_KEY`, `WEB_SEARCH_BACKEND`, `JINA_API_KEY`): read directly by code and **take precedence over** the corresponding `models.yaml` fields — no `${VAR}` reference needed.

## ${VAR} expansion

All string values in `models.yaml` support the `${VAR}` syntax to reference environment variables, expanded when the config is loaded.

### Syntax and Behavior

```yaml
api_key: ${OPENAI_API_KEY}
```

- At load time, `${OPENAI_API_KEY}` is replaced with the value of the `OPENAI_API_KEY` environment variable.
- **If the environment variable is not set**: the literal `${OPENAI_API_KEY}` is kept as-is (no error, but the key may not work for authentication).

!!! example "Expansion example"
    Suppose the env var `OPENAI_API_KEY=sk-abcdef123456`:

    ```yaml
    reasoning:
      api_key: ${OPENAI_API_KEY}   # becomes "sk-abcdef123456" after loading
    ```

    If `OPENAI_API_KEY` is not set:

    ```yaml
    reasoning:
      api_key: ${OPENAI_API_KEY}   # stays as "${OPENAI_API_KEY}"
    ```

!!! tip "How config show displays ${VAR}"
    `anappt config show` masks `api_key` fields:
    - An unexpanded `${VAR}` literal → **shown as-is** (e.g. `${OPENAI_API_KEY}`), so you can see which variable is referenced.
    - An expanded actual value → shown as `****` plus the last 4 characters (e.g. `****3456`).
    - An empty value → shown as `<unset>`.

## Managing Configuration

### `anappt config show`

Displays the current **effective configuration** (the merged result of env > yaml > defaults), with sensitive fields masked and web-section fields annotated with their source.

```bash
anappt config show
```

Example output:

```
Current effective configuration (env > yaml > defaults):
# AnaPPTAgent effective config (env > yaml > default)

reasoning:
  provider: openai
  model: gpt-4o
  api_base: <unset>
  api_key: ****3456
  thinking: <max>

analysis:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_base: <unset>
  api_key: ${ANTHROPIC_API_KEY}
  thinking: FALSE

writing:
  provider: openai
  model: gpt-4o
  api_base: <unset>
  api_key: ****3456
  thinking: <max>

web_search:
  backend: anysearch (env)
  anysearch_api_key: ****5678 (yaml)
  zai_api_key: <unset>

web_fetch:
  jina_api_key: <unset>
```

**Output field meanings**:

| Displayed value | Meaning |
|-----------------|---------|
| `****3456` | Masked actual value (last 4 shown when length ≥ 8) |
| `****` | Masked actual value (only stars when length < 8) |
| `${VAR}` | Unexpanded env-var reference (shown as-is) |
| `<unset>` | Field not configured |
| `<max>` | `thinking` omitted, using maximum effort |
| `FALSE` | `thinking` disabled |
| `(env)` / `(yaml)` / `(default)` | Source annotation for this web field |

!!! note "LLM fields are not source-annotated"
    Because `${VAR}` expansion makes the source (env vs yaml) indistinguishable after loading, `config show` only annotates the `web_search` / `web_fetch` sections with their source, not the LLM role fields.

### `anappt config set`

Interactively configures the three model roles and web capabilities, then writes to `~/.anappt/models.yaml`.

```bash
anappt config set
```

The interactive flow asks, in order:

1. **Three roles** (reasoning → analysis → writing), each asking for:
    - `Provider` (e.g. `openai`, `anthropic`)
    - `Model name` (e.g. `gpt-4o`)
    - `API base` (optional, press Enter to skip)
    - `API key` (may use `${VAR}` to reference an env var)
    - `Thinking` (Enter = max; `FALSE` = off; `low`/`medium`/`high` = effort; integer = token budget)
2. **web_search**:
    - `Backend` (`duckduckgo`/`anysearch`/`zai`, Enter = auto)
    - `AnySearch API key` (optional, may use `${VAR}`)
    - `z.ai API key` (optional, may use `${VAR}`)
3. **web_fetch**:
    - `Jina API key` (optional, Enter = disable)

!!! warning "config set never creates a file in the project directory"
    Configuration is written only to the global `~/.anappt/models.yaml`; **no** `models.yaml` is ever created in the project directory.

## Configuration Examples

=== "Minimal"

    OpenAI only, DuckDuckGo search, no web fetch:

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
    # web_search / web_fetch omitted → DuckDuckGo search, web fetch disabled
    ```

=== "Multi-provider"

    OpenAI reasoning + Anthropic analysis + DeepSeek writing:

    ```yaml
    reasoning:
      provider: openai
      model: o3-mini
      api_key: ${OPENAI_API_KEY}

    analysis:
      provider: anthropic
      model: claude-sonnet-4-20250514
      api_key: ${ANTHROPIC_API_KEY}

    writing:
      provider: deepseek
      model: deepseek-chat
      api_key: ${DEEPSEEK_API_KEY}
    ```

=== "Thinking tuning"

    reasoning high effort, analysis thinking off (faster), writing default max:

    ```yaml
    reasoning:
      provider: openai
      model: o3-mini
      api_key: ${OPENAI_API_KEY}
      thinking: high

    analysis:
      provider: anthropic
      model: claude-sonnet-4-20250514
      api_key: ${ANTHROPIC_API_KEY}
      thinking: FALSE

    writing:
      provider: openai
      model: gpt-4o
      api_key: ${OPENAI_API_KEY}
      # thinking omitted → maximum
    ```

=== "Full configuration"

    Three roles + AnySearch search + Jina fetch + explicit backend:

    ```yaml
    reasoning:
      provider: openai
      model: o3-mini
      api_key: ${OPENAI_API_KEY}
      thinking: high

    analysis:
      provider: anthropic
      model: claude-sonnet-4-20250514
      api_key: ${ANTHROPIC_API_KEY}
      thinking: 8000          # Anthropic budget_tokens

    writing:
      provider: openai
      model: gpt-4o
      api_key: ${OPENAI_API_KEY}

    web_search:
      backend: anysearch
      anysearch_api_key: ${ANYSEARCH_API_KEY}
      zai_api_key: ${ZAI_API_KEY}

    web_fetch:
      jina_api_key: ${JINA_API_KEY}
    ```

## Proxy Configuration

If your network requires a proxy, set the following environment variables (both AnaPPTAgent and the underlying httpx/LiteLLM read them):

```bash
# Linux / macOS
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
export ALL_PROXY=socks5://127.0.0.1:7890
```

```powershell
# Windows PowerShell
$env:HTTP_PROXY = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
$env:ALL_PROXY = "socks5://127.0.0.1:7890"
```

- `HTTPS_PROXY` takes precedence over `HTTP_PROXY`; web search/fetch uses `HTTPS_PROXY` > `HTTP_PROXY` > `ALL_PROXY`.
- `ALL_PROXY` supports the socks5 protocol.

## Migrating from project-level config

!!! warning "Project-level models.yaml is defunct"
    The current version **no longer reads** `<project>/.anappt/models.yaml`. If you used project-level config in an older version, follow these steps to migrate.

**Migration steps**:

1. Check whether a project-level config exists:
    ```bash
    ls <project>/.anappt/models.yaml
    ```
2. Merge its contents into the global config (preserve any existing global config to avoid overwriting):
    ```bash
    # Edit the global config
    # Copy the contents of <project>/.anappt/models.yaml into ~/.anappt/models.yaml
    ```
    Or simply re-run `anappt config set` to reconfigure interactively.
3. Delete the project-level file (optional, to avoid the warning on every run):
    ```bash
    rm <project>/.anappt/models.yaml
    ```
4. Run `anappt config show` to verify the global config loaded correctly.

!!! note "Warning disappears after migration"
    After migrating and deleting the project-level `models.yaml`, running `anappt run` no longer prints the "project-level config is no longer read" warning.

## Troubleshooting

??? question "`config show` shows `${VAR}` instead of a masked value for api_key"
    The corresponding environment variable is **not set**, so `${VAR}` was not expanded. Set the env var (e.g. `export OPENAI_API_KEY=sk-...`), or fill in the actual key directly in yaml (not recommended — risk of leakage).

??? question "`config show` shows `<unset>` for api_key"
    The field is empty in yaml and not referenced via `${VAR}`. Reconfigure with `anappt config set`, or manually edit `~/.anappt/models.yaml`.

??? question "Web search always uses DuckDuckGo even though anysearch is configured"
    Possible causes:
    - Neither the `ANYSEARCH_API_KEY` env var nor the yaml `anysearch_api_key` is set.
    - `backend: anysearch` is set explicitly but the key is missing → a warning is printed and it falls back to DuckDuckGo.
    - The `WEB_SEARCH_BACKEND=duckduckgo` env var overrides the yaml setting (env takes precedence).

    Use `anappt config show` to inspect the effective values and source annotations in the `web_search` section.

??? question "`thinking` is set but doesn't seem to take effect"
    Check whether the provider supports the corresponding parameter:
    - `low`/`medium`/`high` only works for OpenAI (mapped to `reasoning_effort`).
    - Integer N only works for Anthropic (mapped to `budget_tokens`).
    - Other providers (e.g. DeepSeek) **silently skip** the thinking mapping — no error.
    - If calling code explicitly passes `reasoning_effort` or similar kwargs, they override the config value.

??? question "Running `anappt run` says project-level config is no longer read"
    This is a migration notice, not an error. A `<project>/.anappt/models.yaml` exists in the project directory, but the current version no longer reads it. Follow the steps in [Migrating from project-level config](#migrating-from-project-level-config).

??? question "Edited models.yaml but the run doesn't seem to pick it up"
    Make sure you edited `~/.anappt/models.yaml` (global), not a file in the project directory. Run `anappt config show` to confirm the currently loaded effective config.

## Next Steps

Once configured, continue reading:

- [CLI Usage Guide](cli-usage.en.md)
- [Installation Guide](installation.en.md)
- [Report Generation Workflow](report-workflow.en.md)
- [PPT Generation Workflow](ppt-workflow.en.md)
- [Back to Home](index.md)
