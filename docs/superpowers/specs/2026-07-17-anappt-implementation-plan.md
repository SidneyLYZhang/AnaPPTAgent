# AnaPPTAgent 实现计划

> 版本：v1.1 | 日期：2026-07-17 | 基于设计规格 v1.1 | TDD 驱动
>
> v1.1 变更：经审核新增 6 个任务、拆分 2 个任务、前移 dashi-ppt Bridge Phase、修正 async/sync 一致性、补充依赖与配置细节。共 34 个任务。

## 实施原则

1. **严格 TDD**：每个任务先写失败测试 → 看它失败 → 写最少代码 → 看它通过 → 重构 → git commit
2. **隔离执行**：使用 git worktree 隔离任务，避免误操作
3. **任务粒度**：每个任务 2-5 分钟，带精确文件路径与验证步骤
4. **门控不变通**：无测试不提交；无失败测试不写实现；无验证不宣称完成
5. **同步优先**：全部代码采用同步调用（非 async），litellm 同步 API + subprocess 同步调用，对话式 CLI 无需并发
6. **i18n 贯穿**：所有用户可见字符串必须走 `t()` 翻译函数，不硬编码中文

---

## Phase 0：项目脚手架

### Task 0.1 — 初始化 uv 项目

| 属性 | 内容 |
|------|------|
| **文件** | `pyproject.toml` |
| **前置** | 无 |
| **操作** | 1. 执行 `uv init --name anappt`<br>2. 配置 `pyproject.toml`：Python >=3.11, `[project.scripts]` 入口 `anappt = "anappt.cli:main"`<br>3. 创建 `src/anappt/__init__.py`（version = "0.1.0"） |
| **验证** | `uv run python -c "from anappt import __version__; print(__version__)"` → 输出 `0.1.0` |

### Task 0.2 — 安装核心依赖 + 工具链配置

| 属性 | 内容 |
|------|------|
| **文件** | `pyproject.toml`, `ruff.toml` |
| **前置** | Task 0.1 |
| **操作** | 1. 添加运行依赖：`litellm`, `pyyaml`, `rich`, `pandas`, `polars`, `duckdb`, `httpx`, `pydantic`, `duckduckgo-search`, `openpyxl`<br>2. 添加 dev 依赖：`pytest`, `pytest-cov`, `pytest-asyncio`, `ruff`<br>3. 创建 `ruff.toml`：`line-length = 100`, `target-version = "py311"`, 规则集 `E,F,W,I,N,UP`<br>4. 执行 `uv sync` |
| **注意** | `openpyxl` 是 pandas 读取 Excel 的必需引擎。`duckduckgo-search` 包名需在实现时核实 PyPI 最新状态（该包曾更名，API 签名可能变化）。 |
| **验证** | `uv run pytest --version && uv run ruff check --version && uv run python -c "import openpyxl; print('ok')"` → 均正常输出 |

### Task 0.3 — 创建目录结构

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/{stages,llm,tools,io,bridge}/__init__.py`, `tests/__init__.py`, `templates/project/`, `tests/conftest.py` |
| **前置** | Task 0.1 |
| **操作** | 1. 创建 `src/anappt/` 下全部子包的 `__init__.py`<br>2. 创建 `tests/` 目录及 `__init__.py`<br>3. 创建 `templates/project/` 目录<br>4. 创建 `tests/conftest.py`（空壳，Phase 1-2 完成后回头补充 `mock_llm`、`mock_project_dir`、`sample_data` 等共享 fixture） |
| **验证** | `uv run python -c "import anappt.stages; import anappt.llm; import anappt.tools; import anappt.io; import anappt.bridge; print('OK')"` |

### Task 0.4 — 创建项目模板文件

| 属性 | 内容 |
|------|------|
| **文件** | `templates/project/report.yaml.tmpl`, `templates/project/.gitignore.tmpl`, `templates/project/data/.gitkeep`, `templates/project/data/README.md.tmpl` |
| **前置** | Task 0.3 |
| **操作** | 1. 创建 `report.yaml.tmpl`（含 `project:`, `report:`, `delivery:` 三个 section 占位）<br>2. 创建 `.gitignore.tmpl`，内容需**精确区分**：<br>&nbsp;&nbsp;- **忽略**：`.anappt/session_history/`、`__pycache__/`、`.DS_Store`、`*.pyc`、`output/images/`<br>&nbsp;&nbsp;- **保留（不忽略）**：`.anappt/state.yaml`、`.anappt/memory.md`、`.anappt/s2_data_requirement.md`、`.anappt/s3_data_profile.md`、`.anappt/s4_analysis_report.md`<br>3. 创建空 `data/.gitkeep`<br>4. 创建 `data/README.md.tmpl`（埋点/表结构说明占位模板） |
| **验证** | `ls templates/project/` → 四个文件存在，`report.yaml.tmpl` 可用 `pyyaml` 解析 |

---

## Phase 1：I/O 与持久化层

### Task 1.0 — i18n 基础设施

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/i18n.py` |
| **前置** | Task 0.2 |
| **操作** | 1. 实现 locale 检测：读取 `LANG` / `LANGUAGE` 环境变量，默认 `zh`<br>2. 实现消息目录：`src/anappt/locales/zh.json` + `src/anappt/locales/en.json`<br>3. 实现 `t(key: str, **kwargs) -> str` 翻译函数，支持 `{placeholder}` 插值<br>4. 覆盖的 key 范围：CLI 命令提示、阶段名称、门控确认/修改提示、错误消息、S5 报告提醒 |
| **测试** | `tests/test_i18n.py` — 测试 locale 检测、key 查找、fallback 到中文、插值、缺失 key 返回 key 本身 |
| **验证** | `uv run pytest tests/test_i18n.py -v` → 全部通过 |
| **约束** | 后续所有 Stage 和 CLI 任务中的用户可见字符串必须使用 `t()` 函数 |

### Task 1.1 — 配置模型定义

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/io/config.py` |
| **前置** | Task 0.2 |
| **操作** | 用 pydantic BaseModel 定义：<br>`ReportConfig`（project, report, delivery 字段）<br>`ModelRoleConfig`（provider, model, api_base, api_key）<br>`ModelsConfig`（reasoning, analysis, writing）<br>提供 `from_yaml(path)` / `to_yaml()` 方法 |
| **测试** | `tests/io/test_config.py` — 测试序列化/反序列化、环境变量展开（`${VAR}` 语法） |
| **验证** | `uv run pytest tests/io/test_config.py -v` → 全部通过 |

### Task 1.2 — 状态管理

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/io/state.py` |
| **前置** | Task 1.1 |
| **操作** | 定义 `StageStatus(Enum)`, `StageState(BaseModel)`, `PipelineState(BaseModel)`<br>实现 `StateManager` 类：`load()`, `save()`, `get_current_stage()`, `transition(stage_id, status)`<br>实现门控校验：`can_start(stage_id) → bool`<br>实现 `reset()` → 全部重置为 pending（供 `--from-scratch` 使用） |
| **测试** | `tests/io/test_state.py` — 测试状态转换规则（pending→in_progress→awaiting_review→completed），测试 cannot_start_when_prerequisite_not_completed，测试 reset |
| **验证** | `uv run pytest tests/io/test_state.py -v` → 全部通过（至少 7 个 test case） |

### Task 1.3 — 多格式数据加载器

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/io/data_loader.py` |
| **前置** | Task 0.2 |
| **操作** | 实现 `detect_files(data_dir) → list[Path]`（扫描 CSV/Excel/SQLite/DuckDB/Parquet）<br>实现 `load_file(path) → DataFrame`（自动判断格式并加载）<br>实现 `load_all(data_dir) → dict[str, DataFrame]` |
| **测试** | `tests/io/test_data_loader.py` — 用临时文件测试各格式加载（CSV/Excel/SQLite/Parquet），测试格式识别，测试空目录 |
| **验证** | `uv run pytest tests/io/test_data_loader.py -v` → 全部通过 |

### Task 1.4 — GitAutoCommit 类实现

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/io/git_auto.py` |
| **前置** | Task 0.2 |
| **操作** | 实现 `GitAutoCommit` 类：<br>- `__init__(project_dir: Path)`<br>- `is_git_repo() → bool`<br>- `commit_on_stage_complete(stage_id, stage_name, files)` — message: `feat(S{n}): complete {stage_name} — {files}`<br>- `commit_on_confirm(stage_id)` — message: `feat(S{n}): confirm {stage_name}`<br>- `commit_on_exit()` — message: `chore: auto-save on exit`<br>- `git add` 排除 `.anappt/session_history/`<br>- 遵循 Conventional Commits（英文 message）<br>- 非 git 仓库时静默跳过（无报错） |
| **测试** | `tests/io/test_git_auto.py` — 用 `tmp_path` + `git init` 测试三种触发场景的 commit message 格式、排除规则、非 git 仓库的静默跳过 |
| **验证** | `uv run pytest tests/io/test_git_auto.py -v` → 全部通过 |

---

## Phase 2：LLM Provider 层

### Task 2.1 — LLM provider 封装

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/llm/provider.py`, `src/anappt/llm/models.py` |
| **前置** | Task 1.1 |
| **操作** | `models.py`：定义 `ModelRole(Literal["reasoning", "analysis", "writing"])`<br>`provider.py`：实现 `AnaPPTLLM` 类（**同步**）<br>- `__init__(config: ModelsConfig)`<br>- `chat(role: ModelRole, messages, **kwargs) → str` — 同步调用 `litellm.completion()`<br>- `chat_with_tools(role, messages, tools, **kwargs)` — 封装 litellm function calling（供 S4 使用） |
| **测试** | `tests/llm/test_provider.py` — 用 mock 测试角色→模型映射正确性；用 `test` provider（litellm 自带）测试基本调用链路；测试 `chat_with_tools` 的 tool_calls 解析 |
| **验证** | `uv run pytest tests/llm/test_provider.py -v` → 全部通过 |

### Task 2.2 — 全局模型配置管理

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/llm/provider.py`（扩展） |
| **前置** | Task 2.1 |
| **操作** | 实现 `load_global_config() → ModelsConfig`：从 `~/.anappt/models.yaml` 加载<br>实现 `merge_config(global, project) → ModelsConfig`：项目级覆盖全局<br>实现 `save_global_config(config)`：交互式 `anappt config` 写入 |
| **测试** | `tests/llm/test_provider.py` — 测试配置合并逻辑（项目覆盖、缺失回退、环境变量展开、全局配置文件不存在时的默认值） |
| **验证** | `uv run pytest tests/llm/test_provider.py -v` → 全部通过 |

---

## Phase 3：工具层

### Task 3.1 — Web Search：duckduckgo 后端 + 后端选择逻辑

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/tools/web_search.py` |
| **前置** | Task 0.2 |
| **操作** | 1. 定义 `SearchResult` pydantic model（title, url, snippet）<br>2. 定义 `SearchBackend(Enum)`：`DUCKDUCKGO`, `ANYSEARCH`, `ZAI`<br>3. 实现 `get_backend() → SearchBackend`：后端选择逻辑（按 API Key 优先级 + `WEB_SEARCH_BACKEND` 环境变量）<br>4. 实现 duckduckgo 后端 `search_web(query, num_results=5) → list[SearchResult]`<br>5. 代理支持：httpx `trust_env=True`，自动识别 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`<br>6. 定义后端接口 `SearchBackendBase`（抽象类），duckduckgo 为第一个实现 |
| **注意** | `duckduckgo-search` 包名和 API 签名需在实现时核实 PyPI 最新文档 |
| **测试** | `tests/tools/test_web_search.py` — mock 测试后端选择逻辑（四种组合）；测试 duckduckgo 正常返回（mock 或有网络时）；测试代理环境变量读取 |
| **验证** | `uv run pytest tests/tools/test_web_search.py -v` → 全部通过 |

### Task 3.2 — Web Search：AnySearch + z.ai API 客户端

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/tools/web_search.py`（扩展） |
| **前置** | Task 3.1 |
| **操作** | 1. 实现 `AnySearchBackend(SearchBackendBase)`：<br>&nbsp;&nbsp;- 调用 `https://www.anysearch.com/docs#search-api`<br>&nbsp;&nbsp;- 认证：`ANYSEARCH_API_KEY`<br>&nbsp;&nbsp;- 请求/响应解析适配 AnySearch 格式<br>2. 实现 `ZAIBackend(SearchBackendBase)`：<br>&nbsp;&nbsp;- 调用智谱搜索工具 API `https://docs.bigmodel.cn`<br>&nbsp;&nbsp;- 认证：`ZAI_API_KEY`<br>&nbsp;&nbsp;- 请求/响应解析适配 z.ai 格式<br>3. 两个后端均支持系统代理（`trust_env=True`）<br>4. 注册到 `get_backend()` 选择逻辑中 |
| **测试** | `tests/tools/test_web_search.py` — mock httpx 测试两个后端的请求构造、响应解析、错误处理、代理配置 |
| **验证** | `uv run pytest tests/tools/test_web_search.py -v` → 全部通过 |

### Task 3.3 — Web Fetch（Jina Reader）

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/tools/web_fetch.py` |
| **前置** | Task 0.2 |
| **操作** | 实现 `is_available() → bool`（检查 `JINA_API_KEY`）<br>实现 `fetch_url(url) → str`<br>- 请求 `https://r.jina.ai/{url}`<br>- Header: `Authorization: Bearer {JINA_API_KEY}`<br>- 代理：httpx `trust_env=True` |
| **测试** | `tests/tools/test_web_fetch.py` — 测试无 API Key 时 `is_available()` 返回 False；mock 测试正常请求、错误响应、代理配置 |
| **验证** | `uv run pytest tests/tools/test_web_fetch.py -v` → 全部通过 |

### Task 3.4 — Code Execution（Python 沙箱）

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/tools/code_exec.py` |
| **前置** | Task 0.2 |
| **操作** | 定义 `ExecutionResult` pydantic（stdout, stderr, returncode）<br>实现 `execute_python(code, timeout=60, allowed_dirs=None) → ExecutionResult`<br>- subprocess 隔离执行<br>- 限制文件系统访问（仅 `data/` 和临时目录）<br>- 超时控制（subprocess timeout） |
| **测试** | `tests/tools/test_code_exec.py` — 测试正常执行、超时、语法错误、禁止网络访问（mock socket）、限制文件系统访问 |
| **验证** | `uv run pytest tests/tools/test_code_exec.py -v` → 全部通过 |

---

## Phase 4：状态机引擎

### Task 4.1 — 阶段基类 + 核心数据结构

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/stage_base.py`, `src/anappt/types.py` |
| **前置** | Task 1.2 + Task 1.0 |
| **操作** | `types.py`：定义两个核心数据结构：<br>`PipelineContext`：<br>&nbsp;&nbsp;- `project_dir: Path`<br>&nbsp;&nbsp;- `state: StateManager`<br>&nbsp;&nbsp;- `config: ReportConfig`<br>&nbsp;&nbsp;- `llm: AnaPPTLLM`<br>&nbsp;&nbsp;- `tools: dict` (已注册的工具函数)<br>&nbsp;&nbsp;- `ui: InteractiveUI`<br>&nbsp;&nbsp;- `session: SessionLogger`<br>&nbsp;&nbsp;- `git: GitAutoCommit`<br>`StageOutput`：<br>&nbsp;&nbsp;- `status: str` (awaiting_review / failed)<br>&nbsp;&nbsp;- `artifacts: list[Path]` (产出文件路径)<br>&nbsp;&nbsp;- `summary: str` (阶段摘要)<br>&nbsp;&nbsp;- `next_action: str` (提示用户的下一步操作)<br><br>`stage_base.py`：定义抽象基类 `StageBase`：<br>- `stage_id: str`, `stage_name: str`, `model_role: ModelRole`<br>- `run(context: PipelineContext) → StageOutput`（抽象方法，**同步**）<br>- `validate_prerequisites(context) → bool` |
| **测试** | `tests/test_stage_base.py` — 用 mock 子类测试基类生命周期、prerequisites 校验、StageOutput 构建 |
| **验证** | `uv run pytest tests/test_stage_base.py -v` → 全部通过 |

### Task 4.2 — 流水线编排器

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/orchestrator.py` |
| **前置** | Task 4.1 + Task 1.4 |
| **操作** | 实现 `Orchestrator` 类（**同步**）：<br>- `__init__(project_dir: Path)` → 加载全部上下文到 PipelineContext<br>- `run(target_stage=None)` → 从当前阶段执行到目标阶段<br>- `resume()` → 从中断点恢复<br>- `confirm_stage(stage_id)` → 门控确认，调用 `git.commit_on_confirm()`<br>- `revise_stage(stage_id, feedback)` → 重新处理<br>- `reset()` → 重置状态（供 `--from-scratch` 使用）<br>- 阶段产出后自动调用 `git.commit_on_stage_complete()`<br>- 进程退出时调用 `git.commit_on_exit()`（注册 atexit handler） |
| **测试** | `tests/test_orchestrator.py` — 测试阶段顺序执行、中断恢复、门控确认、拒绝跳过、reset、git commit 调用验证（mock GitAutoCommit） |
| **验证** | `uv run pytest tests/test_orchestrator.py -v` → 全部通过 |

### Task 4.3 — Session History 日志

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/io/session.py` |
| **前置** | Task 0.2 + Task 1.0 |
| **操作** | 实现 `SessionLogger` 类：<br>- `__init__(project_dir: Path)`<br>- `log_agent(message: str, stage: str = None)` — 记录 Agent 输出<br>- `log_user(message: str, stage: str = None)` — 记录用户输入<br>- `flush()` — 写入 `.anappt/session_history/YYYY-MM-DD.md`（Markdown 格式）<br>- 同一天追加到同一文件，自动添加时间戳<br>- 使用 `t()` 函数做 header 国际化 |
| **测试** | `tests/io/test_session.py` — 测试日志写入格式、同日追加、多日分文件、flush 时机 |
| **验证** | `uv run pytest tests/io/test_session.py -v` → 全部通过 |

### Task 4.4 — S4 Agent 循环引擎

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/tools/agent_loop.py` |
| **前置** | Task 2.1 + Task 3.1 + Task 3.3 + Task 3.4 |
| **操作** | 定义 `ToolCall` pydantic（name, arguments）<br>定义 `ToolResult` pydantic（name, result, error）<br>实现 `AgentLoop` 类：<br>- `__init__(llm: AnaPPTLLM, tools: dict[str, Callable], model_role: ModelRole)`<br>- `run(system_prompt: str, user_message: str, max_iterations: int = 10) → str`<br>- **循环逻辑**：<br>&nbsp;&nbsp;1. 调用 `llm.chat_with_tools()` 传入 tools schema<br>&nbsp;&nbsp;2. 若 LLM 返回 tool_calls → 执行对应工具 → 将 ToolResult 拼入 messages → 回到步骤 1<br>&nbsp;&nbsp;3. 若 LLM 返回纯文本（无 tool_calls）→ 视为分析完成，返回最终文本<br>&nbsp;&nbsp;4. 超过 max_iterations → 返回当前最佳结果<br>- **工具 schema**：从 Python 函数签名自动生成 JSON Schema（litellm function calling 格式）<br>- **错误处理**：工具执行失败时将错误信息回传给 LLM，让其决定重试或放弃 |
| **测试** | `tests/tools/test_agent_loop.py` — mock LLM 测试：无工具调用直接返回、单轮工具调用、多轮工具调用、max_iterations 截断、工具执行错误回传 |
| **验证** | `uv run pytest tests/tools/test_agent_loop.py -v` → 全部通过 |

### Task 4.5 — Git Auto-Commit 接入编排器

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/orchestrator.py`（扩展） |
| **前置** | Task 4.2 + Task 1.4 |
| **操作** | 在 Orchestrator 中接入 GitAutoCommit（**如果 Task 4.2 已包含此接线则本任务可合并**）：<br>1. `__init__` 中初始化 `self.git = GitAutoCommit(project_dir)`<br>2. 阶段产出写入后：`self.git.commit_on_stage_complete(stage_id, stage_name, artifact_files)`<br>3. `confirm_stage()` 中：`self.git.commit_on_confirm(stage_id)`<br>4. 注册 `atexit.register(self.git.commit_on_exit)`<br>5. Ctrl+C（KeyboardInterrupt）处理：catch 后调用 `commit_on_exit()` 再退出 |
| **测试** | `tests/test_orchestrator.py` — 验证三个触发点的 git commit 调用（mock GitAutoCommit，检查调用参数） |
| **验证** | `uv run pytest tests/test_orchestrator.py -v` → 全部通过 |

---

## Phase 5：dashi-ppt 桥接层

> **Phase 前移说明**：原 Phase 7 前移至此，因为 S6（Task 6.6）依赖 Bridge。Bridge 是纯基础设施，不依赖任何 Stage。

### Task 5.1 — dashi-ppt 桥接实现

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/bridge/dashi_ppt.py` |
| **前置** | Task 0.2 |
| **操作** | 实现 `DashiPPTBridge` 类：<br>- `__init__(project_dir: Path)` — `self.skill_dir = project_dir / ".anappt" / "dashi-ppt-project"`<br>- `check_prerequisites() → list[str]` — 检查 Node.js >= 20、npm、Chrome/Chromium/Edge（`CHROME_PATH`），返回缺失项列表<br>- `install_or_update()` — `subprocess.run(["npx", "dashi-ppt-skill@latest"], cwd=...)`<br>- `generate(prompt: str, theme: str) → Path` — 触发 PPT 生成，返回 `output/presentation.html` 路径<br>- `export(format: str) → Path` — 导出 PPTX/PDF<br>  - pptx: `npm --prefix {skill_dir} run export:pptx -- {output_dir}/presentation.pptx`<br>  - pdf: `npm --prefix {skill_dir} run export:pdf -- {output_dir}/presentation` |
| **测试** | `tests/bridge/test_dashi_ppt.py` — mock subprocess 测试前置检查（Node/npm/Chrome 存在与缺失）、安装命令、生成命令、导出命令、skill_dir 路径正确性 |
| **验证** | `uv run pytest tests/bridge/test_dashi_ppt.py -v` → 全部通过 |

---

## Phase 6：六阶段实现

### Task 6.1 — S1 · 选题与目标定义

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/stages/s1_topic.py` |
| **前置** | Task 4.2 + Task 2.1 + Task 1.0 |
| **操作** | 实现 `S1TopicStage(StageBase)`：<br>- 对话式收集：选题、动机、受众、目标、成功标准<br>- 推理型模型整理为结构化 `report.yaml`<br>- 用户确认后写入项目目录<br>- 所有用户可见字符串使用 `t()` 函数 |
| **测试** | `tests/stages/test_s1_topic.py` — mock LLM 测试：对话流程、report.yaml 生成格式、门控逻辑、i18n 字串 |
| **验证** | `uv run pytest tests/stages/test_s1_topic.py -v` → 全部通过 |

### Task 6.2 — S2 · 数据需求分析

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/stages/s2_data_req.py` |
| **前置** | Task 6.1 |
| **操作** | 实现 `S2DataReqStage(StageBase)`：<br>- 读取 `report.yaml` + `data/` 下说明文档<br>- 推理型模型推导数据需求清单<br>- 产出 `.anappt/s2_data_requirement.md`<br>- **不检查数据是否存在**——纯粹从分析需求出发 |
| **测试** | `tests/stages/test_s2_data_req.py` — mock 测试需求推导、不检查数据存在性、产出文件格式 |
| **验证** | `uv run pytest tests/stages/test_s2_data_req.py -v` → 全部通过 |

### Task 6.3 — S3 · 数据加载与验证

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/stages/s3_data_load.py` |
| **前置** | Task 6.2 + Task 1.3 |
| **操作** | 实现 `S3DataLoadStage(StageBase)`（无 LLM，纯数据处理）：<br>- 扫描 `data/` 目录，调用 `data_loader.load_all()`<br>- 生成数据 profile，**按规格 4.3 节完整实现 6 类统计**：<br>&nbsp;&nbsp;- 基础统计：行数、列数、列类型、空值率<br>&nbsp;&nbsp;- 数值列：min, max, mean, median, std<br>&nbsp;&nbsp;- 分类列：unique 值数量、top 5 值及频次<br>&nbsp;&nbsp;- 日期列：min_date, max_date, span_days<br>- 对照 S2 需求清单检查覆盖度<br>- 若覆盖率不足，提示用户补充数据，可回退 S2<br>- 产出 `.anappt/s3_data_profile.md`（Markdown 表格格式） |
| **测试** | `tests/stages/test_s3_data_load.py` — 用临时数据文件测试 profile 生成（6 类统计完整）、覆盖率检查、回退 S2 逻辑 |
| **验证** | `uv run pytest tests/stages/test_s3_data_load.py -v` → 全部通过 |

### Task 6.4 — S4 · 数据分析（核心阶段）

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/stages/s4_analysis.py` |
| **前置** | Task 6.3 + Task 4.4 |
| **操作** | 实现 `S4AnalysisStage(StageBase)`：<br>- 构造 S4 系统提示词（分析目标 + 数据上下文 + 工具说明）<br>- 注册工具：`search_web` / `fetch_url`（若可用）/ `execute_python`<br>- 调用 `AgentLoop.run()` 执行分析型模型 + 工具循环<br>- 输出分析报告草案 → 用户复核<br>- **迭代循环**：<br>&nbsp;&nbsp;1. 用户反馈 → 构造新的 user_message<br>&nbsp;&nbsp;2. 再次调用 `AgentLoop.run()`，传入历史上下文 + 反馈<br>&nbsp;&nbsp;3. 更新 `.anappt/s4_analysis_report.md`<br>&nbsp;&nbsp;4. 再次提交用户确认<br>&nbsp;&nbsp;5. 循环直到用户满意<br>- 若 `fetch_url` 不可用（无 JINA_API_KEY），在提示中告知用户<br>- S4 不强制生成图表，按需生成至 `output/images/` |
| **测试** | `tests/stages/test_s4_analysis.py` — mock AgentLoop 测试：初始分析、迭代流程、fetch 不可用降级、门控确认 |
| **验证** | `uv run pytest tests/stages/test_s4_analysis.py -v` → 全部通过 |

### Task 6.5 — S5 · 报告生成

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/stages/s5_report.py` |
| **前置** | Task 6.4 |
| **操作** | 实现 `S5ReportStage(StageBase)`：<br>- 写作型模型读取 S4 分析报告<br>- 生成标准结构报告：摘要 → 背景与目标 → 数据来源与方法 → 核心发现（多章节）→ 结论与建议 → 附录<br>- 产出 `output/final_report.md`<br>- **门控行为**（按规格 4.5）：完成后明确提醒用户打开 `output/final_report.md` 查看/修改<br>- 支持两种修改路径：<br>&nbsp;&nbsp;1. 用户直接编辑文件 → 确认<br>&nbsp;&nbsp;2. 用户对话提出修改意见 → Agent 优化报告 → 再确认<br>- 多次往返直到用户满意 |
| **测试** | `tests/stages/test_s5_report.py` — mock 测试报告结构完整性、修改迭代流程、门控提醒文案 |
| **验证** | `uv run pytest tests/stages/test_s5_report.py -v` → 全部通过 |

### Task 6.6 — S6 · PPT 生成

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/stages/s6_ppt.py` |
| **前置** | Task 6.5 + **Task 5.1** |
| **操作** | 实现 `S6PPTStage(StageBase)`：<br>- 写作型模型读取 `output/final_report.md`，构造 dashi-ppt-skill prompt（主题 + 受众 + 核心结论 + 页数 + 风格偏好）<br>- 用户从 12 套主题中选择<br>- 调用 `DashiPPTBridge.generate()` 生成 HTML<br>- 用户在浏览器编辑确认后 → 调用 `DashiPPTBridge.export("pptx")` 导出<br>- 产出 `output/presentation.html` + `output/presentation.pptx` |
| **测试** | `tests/stages/test_s6_ppt.py` — mock 测试 prompt 生成、主题选择流程、Bridge 调用、门控确认 |
| **验证** | `uv run pytest tests/stages/test_s6_ppt.py -v` → 全部通过 |

---

## Phase 7：CLI 与交互层

### Task 7.0 — 项目初始化逻辑

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/project.py` |
| **前置** | Task 0.4 + Task 1.2 |
| **操作** | 实现 `create_project(name: str, base_dir: Path = None) → Path`：<br>1. 创建项目目录 `base_dir / name`<br>2. 创建子目录：`data/`, `output/`, `output/images/`, `.anappt/`, `.anappt/session_history/`<br>3. 渲染模板：`report.yaml.tmpl` → `report.yaml`，`.gitignore.tmpl` → `.gitignore`，`data/README.md.tmpl` → `data/README.md`<br>4. 创建 `.anappt/memory.md`（空文件）<br>5. 初始化 `.anappt/state.yaml`（全部 6 阶段 pending）<br>6. 创建 `output/.gitkeep`、`output/images/.gitkeep`<br>7. 生成项目 `README.md`（含项目名和基本说明）<br>8. 执行 `git init` + 首次 `git add . && git commit -m "chore: init project"` |
| **测试** | `tests/test_project.py` — 用 `tmp_path` 测试目录结构完整性、模板渲染、state.yaml 初始化、git 初始化 |
| **验证** | `uv run pytest tests/test_project.py -v` → 全部通过 |

### Task 7.1 — CLI 命令骨架

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/cli.py` |
| **前置** | Task 7.0 + Task 4.2 + Task 0.4 |
| **操作** | 使用 `rich` + `argparse` 实现：<br>`anappt new <name>` → 调用 `create_project()`<br>`anappt run [--stage S{n}]` → 启动/恢复流水线<br>`anappt run --from-scratch` → 调用 `orchestrator.reset()` 后重新开始<br>`anappt status` → 显示阶段状态（rich Table）<br>`anappt config` → 交互式配置 LLM 模型<br>`anappt config show` → 显示当前 LLM 配置<br>注册 `atexit` + `KeyboardInterrupt` handler 调用 `git.commit_on_exit()` |
| **测试** | `tests/test_cli.py` — 测试各命令参数解析（含 `--from-scratch`），测试 `new` 命令产出目录结构，测试 `status` 输出格式 |
| **验证** | `uv run anappt --help` → 显示命令列表；`uv run anappt new test_proj && ls test_proj/` → 看到 report.yaml、data/、.anappt/、output/ |

### Task 7.2 — 对话式终端 UI

| 属性 | 内容 |
|------|------|
| **文件** | `src/anappt/cli.py`（扩展） |
| **前置** | Task 7.1 + Task 1.0 |
| **操作** | 实现 `InteractiveUI` 类（基于 rich）：<br>- `render_agent(message: str)` — Panel + Markdown 渲染 Agent 输出<br>- `render_stage_status(stages: list)` — Table 显示阶段状态<br>- `prompt_user(prompt: str) → str` — `rich.prompt.Prompt.ask()` 收集用户输入<br>- `confirm_gate(stage_name: str) → str` — 门控确认（返回 "confirm" 或修改意见）<br>- `show_error(message: str)` — 错误提示样式<br>- 所有文案使用 `t()` 函数，支持中英文切换 |
| **测试** | `tests/test_cli.py` — 测试 UI 输出格式化、i18n 字符串读取、confirm_gate 返回值 |
| **验证** | 人工验证（CLI 交互类测试难自动化，核心逻辑通过单元测试覆盖） |

---

## Phase 8：集成测试

### Task 8.1 — 集成测试：完整流水线

| 属性 | 内容 |
|------|------|
| **文件** | `tests/integration/test_full_pipeline.py` |
| **前置** | Task 6.6 + Task 7.1 |
| **操作** | 端到端测试：`create_project()` → S1-S6 全部用 mock LLM + mock Bridge 跑通 → 检查产出文件完整性：<br>- `report.yaml` 存在且可解析<br>- `.anappt/s2_data_requirement.md` 存在<br>- `.anappt/s3_data_profile.md` 存在<br>- `.anappt/s4_analysis_report.md` 存在<br>- `output/final_report.md` 存在<br>- `output/presentation.html` 存在（mock）<br>- git log 有对应 commit 记录 |
| **验证** | `uv run pytest tests/integration/test_full_pipeline.py -v` → 通过 |

### Task 8.2 — 集成测试：中断恢复

| 属性 | 内容 |
|------|------|
| **文件** | `tests/integration/test_resume.py` |
| **前置** | Task 8.1 |
| **操作** | 测试：S3 完成并确认后退出 → 重新创建 Orchestrator → 正确从 S4 继续<br>测试：S4 awaiting_review 状态退出 → 恢复后正确显示 awaiting_review 而非重新执行<br>测试：`--from-scratch` 重置后从 S1 开始 |
| **验证** | `uv run pytest tests/integration/test_resume.py -v` → 通过 |

---

## Phase 9：文档与收尾

### Task 9.1 — README + 使用指南

| 属性 | 内容 |
|------|------|
| **文件** | `README.md` |
| **前置** | Phase 7 完成 |
| **操作** | 中英文双语 README：安装（uv）、配置（models.yaml + 环境变量）、快速开始、命令参考、项目结构说明、dashi-ppt-skill 依赖说明 |
| **验证** | 人工审阅 |

### Task 9.2 — 全量验证

| 属性 | 内容 |
|------|------|
| **前置** | 全部任务完成 |
| **操作** | `uv run pytest -v --cov=anappt` → 全部通过 + 覆盖率 > 80%<br>`uv run ruff check src/ tests/` → 无错误<br>手动冒烟测试：`anappt new demo && cd demo && anappt run`（需配置真实 LLM） |
| **验证** | 贴出真实输出 |

---

## 依赖关系总览

```
0.1 ─→ 0.2 ─→ 0.3 ─→ 0.4
         │       │
    ┌────┘       │
    ▼            │
   1.0 ─→ 1.1 ─→ 1.2 ─→ 1.3
    │      │      │
    │      │      ▼
    │      │     1.4
    │      │      │
    │      ▼      │
    │     2.1 ─→ 2.2
    │      │
    │      │     3.1 ─→ 3.2
    │      │      │       │
    │      │     3.3      3.4
    │      │      │       │
    │      │      └───┬───┘
    │      │          │
    │      │     4.4 ◄─┘
    │      │          │
    │      ▼          │
    │     4.1 ─→ 4.2 ─→ 4.3
    │              │
    │              ▼
    │             4.5
    │              │
    │     5.1 ◄─────┘ (Bridge, 独立但 S6 依赖它)
    │      │
    │      ▼
    │     6.1 ─→ 6.2 ─→ 6.3 ─→ 6.4 ─→ 6.5 ─→ 6.6
    │                                    │      │
    │                                    │      ▼
    │     7.0 ─→ 7.1 ─→ 7.2              │     (done)
    │              │                     │
    │              ▼                     │
    │             8.1 ─→ 8.2 ─→ 9.1 ─→ 9.2
    └──────────────┘
```

## v1.0 → v1.1 变更记录

| # | 变更类型 | 内容 | 对应审核项 |
|---|---------|------|-----------|
| 1 | 新增 Task | 1.0 i18n 基础设施 | P0-1 |
| 2 | 新增 Task | 1.4 GitAutoCommit 类实现（从 Phase 8 前移至 Phase 1） | P0-5 |
| 3 | 新增 Task | 3.2 AnySearch + z.ai API 客户端（从 3.1 拆出） | P1-11 |
| 4 | 新增 Task | 4.3 Session History 日志 | P0-2 |
| 5 | 新增 Task | 4.4 S4 Agent 循环引擎 | P0-3 |
| 6 | 新增 Task | 4.5 Git Auto-Commit 接入编排器 | P0-5 |
| 7 | 新增 Task | 7.0 项目初始化逻辑（从 7.1 拆出） | P0-4 |
| 8 | Phase 前移 | dashi-ppt Bridge 从 Phase 7 前移至 Phase 5 | P1-12 |
| 9 | 修正 | Task 4.1 去掉 async，统一为同步 | P1-6 |
| 10 | 扩展 | Task 4.1 显式定义 PipelineContext + StageOutput 字段 | P1-7 |
| 11 | 补充 | Task 0.2 添加 openpyxl 依赖 + ruff.toml 配置 | P1-10, P2-13 |
| 12 | 补充 | Task 0.2 注明 duckduckgo-search 包名核实 | P2-14 |
| 13 | 补充 | Task 0.4 .gitignore.tmpl 精确区分忽略/保留 | P2-15 |
| 14 | 补充 | Task 0.3 注明 conftest.py 后续补充 fixture 时机 | P2-16 |
| 15 | 补充 | Task 5.3(→6.3) S3 数据 Profile 展开 6 类统计 | P1-9 |
| 16 | 补充 | Task 6.1(→7.1) 添加 --from-scratch 标志 | P1-8 |

## 任务清单汇总

| Phase | 任务数 | 说明 |
|-------|--------|------|
| 0. 脚手架 | 4 | uv 初始化、依赖+工具链、目录结构、模板文件 |
| 1. I/O 持久化 | 5 | i18n、配置模型、状态管理、数据加载、GitAutoCommit |
| 2. LLM Provider | 2 | litellm 封装、全局配置管理 |
| 3. 工具层 | 4 | Web Search(duckduckgo)、Web Search(AnySearch+z.ai)、Web Fetch、Code Exec |
| 4. 状态机引擎 | 5 | 阶段基类+数据结构、编排器、Session日志、Agent循环、Git接入 |
| 5. dashi-ppt 桥接 | 1 | Bridge 实现（前移） |
| 6. 六阶段实现 | 6 | S1-S6 |
| 7. CLI 交互层 | 3 | 项目初始化、CLI骨架、对话UI |
| 8. 集成测试 | 2 | 全流程、中断恢复 |
| 9. 文档收尾 | 2 | README、全量验证 |
| **合计** | **34** | |

---

> **下一步**：此实现计划 v1.1 已纳入全部 16 项审核改进，可进入实施阶段。按 Phase 0 → 1 → ... → 9 顺序逐任务 TDD 实施。
