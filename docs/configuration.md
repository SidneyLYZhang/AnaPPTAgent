# 配置指引

AnaPPTAgent 的所有 LLM 与 Web 能力配置集中在一个**全局唯一**的文件 `~/.anappt/models.yaml` 中。本页详细说明配置文件的位置、优先级、完整 schema、`thinking` 字段语义、Web 搜索/读取配置、环境变量、`${VAR}` 展开、`config show` / `config set` 命令、多 provider 配置示例、代理设置、迁移与故障排查。

!!! info "简略说明 vs 详细指引"
    [CLI 使用指南](cli-usage.md) 中的"全局配置文件"段提供了简略说明;本页为完整参考。首次配置或遇到问题时请阅读本页。

## 配置文件位置

| 项目 | 值 |
|------|-----|
| 文件路径 | `~/.anappt/models.yaml`(`~` 即用户主目录) |
| 创建方式 | `anappt config set` 交互式生成,或手动创建 |
| 读取时机 | 每次运行 `anappt run` / `resume` / `interactive` / `config show` 时加载 |
| 写入时机 | `anappt config set` 完成交互后写入 |

!!! warning "项目级 models.yaml 不再生效"
    早期版本支持在项目目录 `<project>/.anappt/models.yaml` 下放置配置。**当前版本不再读取项目级 models.yaml**。若检测到该文件,会打印警告:

    ```
    项目级配置文件 <project>/.anappt/models.yaml 不再生效,请将其内容迁移到 ~/.anappt/models.yaml
    ```

    迁移方法见[从项目级配置迁移](#从项目级配置迁移)。

## 配置优先级

AnaPPTAgent 对所有可被环境变量覆盖的配置项统一遵循以下优先级:

```
环境变量 (env)  >  models.yaml (yaml)  >  默认值 (default)
```

- **环境变量优先**:当环境变量与 `models.yaml` 同时配置同一项时,**以环境变量的值为准**。
- **默认值兜底**:环境变量与 `models.yaml` 均未配置时,使用内置默认值。
- **适用范围**:Web 搜索的 backend 与各 API key、Web 读取的 Jina key 均遵循此优先级。LLM 角色的 `api_key` 因支持 `${VAR}` 展开(见下文),其"来源"在加载后已不可区分,故 `config show` 不对 LLM 字段标注来源。

!!! tip "推荐做法"
    将 API key 通过 `${VAR}` 引用环境变量写入 `models.yaml`(如 `api_key: ${OPENAI_API_KEY}`),既安全又能享受环境变量优先的便利。详见 [${VAR} 环境变量展开](#var-环境变量展开)。

## 完整 Schema 参考

`models.yaml` 的完整结构如下:

```yaml
reasoning:
  provider: ""              # 必填,provider 标识
  model: ""                 # 必填,模型名
  api_base: null            # 可选,自定义 API 端点
  api_key: null             # 可选,API key(建议用 ${VAR})
  thinking: null            # 可选,思考强度(见 thinking 字段详解)

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

web_search:                 # 可选段,缺省使用 DuckDuckGo
  backend: null             # 可选: duckduckgo | anysearch | zai
  anysearch_api_key: null   # 可选,环境变量优先
  zai_api_key: null         # 可选,环境变量优先

web_fetch:                  # 可选段,缺省禁用
  jina_api_key: null        # 可选,环境变量优先
```

### 字段说明

| 字段 | 类型 | 是否可选 | 默认值 | 说明 |
|------|------|---------|--------|------|
| `*.provider` | string | 必填 | `""` | provider 标识,如 `openai`、`anthropic`、`deepseek`。空字符串视为 OpenAI |
| `*.model` | string | 必填 | `""` | 模型名,如 `gpt-4o`、`claude-sonnet-4-20250514` |
| `*.api_base` | string \| null | 可选 | `null` | 自定义 API 端点(用于代理或兼容接口) |
| `*.api_key` | string \| null | 可选 | `null` | API key,建议用 `${VAR}` 引用环境变量 |
| `*.thinking` | string \| int \| bool \| null | 可选 | `null` | 思考强度,详见 [thinking 字段详解](#thinking-字段详解) |
| `web_search.backend` | string \| null | 可选 | `null`(自动) | 搜索后端:`duckduckgo` / `anysearch` / `zai` |
| `web_search.anysearch_api_key` | string \| null | 可选 | `null` | AnySearch 后端 key,环境变量 `ANYSEARCH_API_KEY` 优先 |
| `web_search.zai_api_key` | string \| null | 可选 | `null` | z.ai 后端 key,环境变量 `ZAI_API_KEY` 优先 |
| `web_fetch.jina_api_key` | string \| null | 可选 | `null` | Jina Reader key,环境变量 `JINA_API_KEY` 优先 |

## LLM 模型角色

AnaPPTAgent 的 6 阶段流水线(S1-S6)使用三种模型角色,每种角色可独立配置 provider 与模型:

| 角色 | 覆盖阶段 | 用途 |
|------|---------|------|
| `reasoning` | S1-S2 | 选题定义、数据需求分析 |
| `analysis` | S4 | 数据分析(工具调用) |
| `writing` | S5-S6 | 报告撰写、PPT 生成 |

!!! note "S3 不调用 LLM"
    S3(数据加载与校验)为纯本地处理,不调用 LLM,因此不使用任何模型角色。

支持所有 [LiteLLM](https://docs.litellm.ai/) 兼容的 provider,包括但不限于 OpenAI、Anthropic、DeepSeek、Azure OpenAI、通义千问、Moonshot 等。`provider` 字段的值会影响 `thinking` 字段的映射(见下文)。

## thinking 字段详解

`thinking` 字段控制该角色调用 LLM 时的**思考强度**(reasoning effort)。它是一个可选的、类型灵活的字段。

### 语义总表

| `thinking` 值 | 含义 | OpenAI 行为 | Anthropic 行为 | 其他 provider |
|--------------|------|------------|---------------|--------------|
| 缺省 / `null` | 使用模型最大思考强度 | 传 `reasoning_effort: "high"` | 不传参(用默认最大) | 不传参 |
| `FALSE` / `OFF`(大小写不敏感) | 关闭思考 | 传 `reasoning_effort: "minimal"` | 不传参 | 不传参 |
| `low` / `medium` / `high` | 按指定强度 | 传 `reasoning_effort: <值>` | 不传参(静默跳过) | 静默跳过 |
| 整数 N(如 `8000`) | 按 token 预算 | 静默跳过 | 传 `thinking: {type: "enabled", budget_tokens: N}` | 静默跳过 |

!!! tip "缺省即最大"
    不写 `thinking` 字段时,AnaPPTAgent 会为 OpenAI o 系列等已知 provider **主动**传"最大"参数(`reasoning_effort: "high"`),确保默认行为是最大思考强度。对于 Anthropic 等默认即为最大思考的 provider,则不传参以使用其默认值。

!!! note "不支持的 provider 不会报错"
    当 `thinking` 设为 `low`/`medium`/`high` 或整数,但 provider 不支持对应参数时,AnaPPTAgent 会**静默跳过**该映射,不会报错。模型仍按其默认行为运行。

### Provider 识别规则

`thinking` 的映射取决于 provider 字符串的匹配(大小写不敏感):

| 判定 | 条件 | 适用示例 |
|------|------|---------|
| OpenAI | `provider` 含 `openai`,或为空字符串 `""` | `openai`、`azure` 配 OpenAI 模型时通常也匹配 |
| Anthropic | `provider` 含 `anthropic` 或 `claude` | `anthropic`、`claude` |
| 其他 | 不匹配上述 | `deepseek`、`moonshot` 等 → thinking 映射被跳过 |

### YAML 示例

```yaml
reasoning:
  provider: openai
  model: o3-mini
  api_key: ${OPENAI_API_KEY}
  thinking: high              # 显式高强度

analysis:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: ${ANTHROPIC_API_KEY}
  thinking: FALSE             # 关闭思考(加速 S4)

writing:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}
  # thinking 缺省 → 最大思考强度
```

## Web 搜索配置

`web_search` 段控制 S4 阶段数据分析时的联网搜索能力。AnaPPTAgent 支持三种搜索后端。

### 后端选择逻辑

搜索后端按以下优先级确定:

1. **环境变量 `WEB_SEARCH_BACKEND`**(若设为有效值 `duckduckgo` / `anysearch` / `zai`)
2. **`models.yaml` 中的 `web_search.backend`**
3. **基于可用 API key 自动选择**:同时有 AnySearch 与 z.ai key 时优先 AnySearch;只有 z.ai key 时用 z.ai;无任何 key 时用 DuckDuckGo

!!! warning "显式 backend 缺 key 时回退"
    若显式指定 `backend: anysearch` 但未配置 `ANYSEARCH_API_KEY`(环境变量与 yaml 均无),会打印警告并**回退到 DuckDuckGo**。`zai` 同理。

### 三种后端配置

=== "DuckDuckGo(默认,无需 key)"

    免费、无需 API key,但可能受限速影响。无需任何配置即可使用:

    ```yaml
    # 不写 web_search 段,或写为:
    web_search:
      backend: duckduckgo
    ```

=== "AnySearch"

    需配置 `ANYSEARCH_API_KEY`(环境变量优先于 yaml):

    ```yaml
    web_search:
      backend: anysearch
      anysearch_api_key: ${ANYSEARCH_API_KEY}
    ```

=== "z.ai(智谱)"

    需配置 `ZAI_API_KEY`(环境变量优先于 yaml):

    ```yaml
    web_search:
      backend: zai
      zai_api_key: ${ZAI_API_KEY}
    ```

!!! tip "自动选择模式"
    不设 `backend` 字段时,AnaPPTAgent 会根据已配置的 key 自动选择后端。这是最省心的方式:

    ```yaml
    web_search:
      anysearch_api_key: ${ANYSEARCH_API_KEY}
      # backend 缺省 → 检测到 anysearch key 即用 AnySearch
    ```

## Web 读取配置

`web_fetch` 段控制 S4 阶段的网页内容读取能力,使用 [Jina Reader](https://r.jina.ai/) 服务将网页转为 Markdown。

- **默认禁用**:不配置 `web_fetch` 段或不设 `jina_api_key` 时,Web 读取功能关闭,S4 不会注册 `fetch_url` 工具。
- **启用方式**:配置 `jina_api_key`,环境变量 `JINA_API_KEY` 优先于 yaml。

```yaml
web_fetch:
  jina_api_key: ${JINA_API_KEY}
```

!!! note "Web 读取与 Web 搜索相互独立"
    Web 搜索(DuckDuckGo/AnySearch/z.ai)与 Web 读取(Jina Reader)是两个独立的能力,可分别启用或禁用。例如可以只开搜索、不开读取。

## 环境变量参考

| 环境变量 | 说明 | 是否优先于 models.yaml |
|---------|------|----------------------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | —(通过 `${VAR}` 引用) |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | —(通过 `${VAR}` 引用) |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | —(通过 `${VAR}` 引用) |
| `ANYSEARCH_API_KEY` | AnySearch 搜索后端密钥 | ✅ 优先于 `web_search.anysearch_api_key` |
| `ZAI_API_KEY` | z.ai 搜索后端密钥 | ✅ 优先于 `web_search.zai_api_key` |
| `WEB_SEARCH_BACKEND` | 显式指定搜索后端(`duckduckgo`/`anysearch`/`zai`) | ✅ 优先于 `web_search.backend` |
| `JINA_API_KEY` | Jina Reader 网页读取密钥 | ✅ 优先于 `web_fetch.jina_api_key` |
| `HTTP_PROXY` | HTTP 代理地址 | — |
| `HTTPS_PROXY` | HTTPS 代理地址 | — |
| `ALL_PROXY` | 全局代理地址(支持 socks5) | — |
| `LANG` | 语言选择:`zh_CN.UTF-8`(默认)或 `en_US.UTF-8` | — |

!!! note "两类环境变量"
    - **LLM API key**(`OPENAI_API_KEY` 等):通过 `models.yaml` 中的 `${VAR}` 语法引用,在加载时展开。它们不直接被代码读取,而是经 `${VAR}` 间接生效。
    - **Web 配置环境变量**(`ANYSEARCH_API_KEY`、`ZAI_API_KEY`、`WEB_SEARCH_BACKEND`、`JINA_API_KEY`):被代码直接读取,**优先于** `models.yaml` 中的对应字段,无需 `${VAR}` 引用。

## ${VAR} 环境变量展开

`models.yaml` 中所有字符串值支持 `${VAR}` 语法引用环境变量,在加载配置时展开。

### 语法与行为

```yaml
api_key: ${OPENAI_API_KEY}
```

- 加载时,`${OPENAI_API_KEY}` 会被替换为环境变量 `OPENAI_API_KEY` 的值。
- **若环境变量未设置**:保留字面量 `${OPENAI_API_KEY}` 不展开(不会报错,但该 key 可能无法用于认证)。

!!! example "展开示例"
    假设环境变量 `OPENAI_API_KEY=sk-abcdef123456`:

    ```yaml
    reasoning:
      api_key: ${OPENAI_API_KEY}   # 加载后变为 "sk-abcdef123456"
    ```

    若 `OPENAI_API_KEY` 未设置:

    ```yaml
    reasoning:
      api_key: ${OPENAI_API_KEY}   # 保留为 "${OPENAI_API_KEY}"
    ```

!!! tip "config show 如何显示 ${VAR}"
    `anappt config show` 对 `api_key` 字段做掩码处理:
    - 未展开的 `${VAR}` 字面量 → **原样显示**(如 `${OPENAI_API_KEY}`),便于你看出引用了哪个变量。
    - 已展开的实际值 → 显示 `****` 加末 4 位(如 `****3456`)。
    - 空值 → 显示 `<unset>`。

## 管理配置

### `anappt config show`

显示当前**有效配置**(env > yaml > 默认值的合并结果),敏感字段掩码,Web 段字段标注来源。

```bash
anappt config show
```

输出示例:

```
当前有效配置 (env > yaml > 默认值):
# AnaPPTAgent 有效配置 (env > yaml > default)

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

**输出字段说明**:

| 显示值 | 含义 |
|-------|------|
| `****3456` | 实际值掩码(长度 ≥ 8 时显示末 4 位) |
| `****` | 实际值掩码(长度 < 8 时仅显示星号) |
| `${VAR}` | 未展开的环境变量引用(原样显示) |
| `<unset>` | 该字段未配置 |
| `<max>` | `thinking` 缺省,使用最大思考强度 |
| `FALSE` | `thinking` 已关闭 |
| `(env)` / `(yaml)` / `(default)` | 该 Web 字段的来源标注 |

!!! note "LLM 字段不标注来源"
    由于 `${VAR}` 展开后 LLM 字段的来源(env 还是 yaml)已不可区分,`config show` 仅对 `web_search` / `web_fetch` 段标注来源,不对 LLM 角色字段标注。

### `anappt config set`

交互式配置三个模型角色与 Web 能力,完成后写入 `~/.anappt/models.yaml`。

```bash
anappt config set
```

交互流程依次询问:

1. **三个角色**(reasoning → analysis → writing),每个角色询问:
    - `Provider`(如 `openai`、`anthropic`)
    - `Model name`(如 `gpt-4o`)
    - `API base`(可选,直接回车跳过)
    - `API key`(可用 `${VAR}` 引用环境变量)
    - `Thinking`(回车 = 最大;`FALSE` = 关闭;`low`/`medium`/`high` = 强度;整数 = token 预算)
2. **web_search**:
    - `Backend`(`duckduckgo`/`anysearch`/`zai`,回车 = 自动)
    - `AnySearch API key`(可选,可用 `${VAR}`)
    - `z.ai API key`(可选,可用 `${VAR}`)
3. **web_fetch**:
    - `Jina API key`(可选,回车 = 禁用)

!!! warning "config set 不会在项目目录生成文件"
    配置仅写入全局 `~/.anappt/models.yaml`,**不**在项目目录下创建任何 `models.yaml`。

## 配置示例

=== "最小配置"

    仅使用 OpenAI,DuckDuckGo 搜索,无 Web 读取:

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
    # web_search / web_fetch 缺省 → DuckDuckGo 搜索,禁用 Web 读取
    ```

=== "多 provider"

    OpenAI 推理 + Anthropic 分析 + DeepSeek 写作:

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

=== "thinking 调优"

    reasoning 高强度,analysis 关闭思考(加速),writing 默认最大:

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
      # thinking 缺省 → 最大
    ```

=== "完整配置"

    三角色 + AnySearch 搜索 + Jina 读取 + 显式 backend:

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

## 代理配置

若网络环境需要代理,设置以下环境变量(AnaPPTAgent 与底层 httpx/LiteLLM 均会读取):

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

- `HTTPS_PROXY` 优先于 `HTTP_PROXY`,Web 搜索/读取会使用 `HTTPS_PROXY` > `HTTP_PROXY` > `ALL_PROXY`。
- `ALL_PROXY` 支持 socks5 协议。

## 从项目级配置迁移

!!! warning "项目级 models.yaml 已失效"
    当前版本**不再读取** `<project>/.anappt/models.yaml`。如果你在旧版本中使用了项目级配置,请按以下步骤迁移。

**迁移步骤**:

1. 检查项目目录下是否存在旧配置:
    ```bash
    ls <project>/.anappt/models.yaml
    ```
2. 将其内容合并到全局配置(注意保留已有的全局配置,避免覆盖):
    ```bash
    # 编辑全局配置
    # 将 <project>/.anappt/models.yaml 的内容复制到 ~/.anappt/models.yaml
    ```
    或直接用 `anappt config set` 重新交互式配置。
3. 删除项目级旧文件(可选,避免每次运行时看到警告):
    ```bash
    rm <project>/.anappt/models.yaml
    ```
4. 运行 `anappt config show` 验证全局配置已正确加载。

!!! note "迁移后警告消失"
    迁移并删除项目级 `models.yaml` 后,运行 `anappt run` 时不再出现"项目级配置文件不再生效"的警告。

## 故障排查

??? question "`config show` 中 api_key 显示 `${VAR}` 而非掩码值"
    说明对应的环境变量**未设置**,`${VAR}` 未被展开。请设置该环境变量(如 `export OPENAI_API_KEY=sk-...`),或直接在 yaml 中填写实际 key 值(不推荐,存在泄露风险)。

??? question "`config show` 中 api_key 显示 `<unset>`"
    该字段在 yaml 中为空且未通过 `${VAR}` 引用环境变量。请用 `anappt config set` 重新配置,或手动编辑 `~/.anappt/models.yaml`。

??? question "Web 搜索总是用 DuckDuckGo,即使配置了 anysearch"
    可能原因:
    - 环境变量 `ANYSEARCH_API_KEY` 与 yaml 中 `anysearch_api_key` **均未配置**。
    - 显式设了 `backend: anysearch` 但缺 key → 会打印警告并回退 DuckDuckGo。
    - 环境变量 `WEB_SEARCH_BACKEND=duckduckgo` 覆盖了 yaml 设置(环境变量优先)。

    用 `anappt config show` 查看 `web_search` 段的有效值与来源标注来定位。

??? question "`thinking` 设了值但似乎没生效"
    检查 provider 是否支持对应参数:
    - `low`/`medium`/`high` 仅对 OpenAI 生效(映射为 `reasoning_effort`)。
    - 整数 N 仅对 Anthropic 生效(映射为 `budget_tokens`)。
    - 其他 provider(如 DeepSeek)会**静默跳过** thinking 映射,不报错。
    - 若调用方代码显式传了 `reasoning_effort` 等 kwargs,会覆盖配置值。

??? question "运行 `anappt run` 提示项目级配置不再生效"
    这是迁移提示,非错误。项目目录下存在 `<project>/.anappt/models.yaml`,但当前版本不再读取它。按[从项目级配置迁移](#从项目级配置迁移)步骤处理即可。

??? question "修改了 models.yaml 但运行时似乎没读到"
    确认你编辑的是 `~/.anappt/models.yaml`(全局),而非项目目录下的文件。运行 `anappt config show` 确认当前加载的有效配置。

## 下一步

配置完成后,继续阅读:

- [CLI 使用指南](cli-usage.md)
- [安装指南](installation.md)
- [报告生成流程](report-workflow.md)
- [PPT 生成流程](ppt-workflow.md)
- [返回首页](index.md)
