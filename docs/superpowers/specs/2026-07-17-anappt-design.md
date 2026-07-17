# AnaPPTAgent 设计规格

> 版本：v1.1 | 日期：2026-07-17 | 状态：待复核

## 1. 概述

### 1.1 产品定位

AnaPPTAgent 是一个专注于**分析报告撰写**与**PPT 自动生成**的独立 Agent 工具。它以项目目录为工作单元，通过六阶段门控流水线，引导分析师从模糊想法走到最终交付物（分析报告 + 可编辑 PPTX）。

### 1.2 目标用户

- **主要用户**：数据分析师、商业分析师、业务分析师、数据科学研究员
- **技术水平**：参差不齐，需要良好的引导式交互
- **交互方式**：对话式终端 UI（CLI + rich 库风格）

### 1.3 核心价值

1. **全流程统筹**：从选题动机到运营建议，Agent 统一管理所有环节
2. **门控确认**：每个关键产出都需用户确认后才能推进，避免方向性错误
3. **可恢复**：状态持久化在项目目录，中断后随时恢复
4. **可追溯**：Git 版本管理 + 完整项目目录自包含
5. **灵活 LLM**：支持多种在线 API 和本地模型，不同阶段可配置不同模型

### 1.4 技术栈

| 维度 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | 分析师生态的 lingua franca |
| 包管理 | uv | 快速、现代、兼容 pip |
| LLM 抽象 | litellm | 覆盖 100+ provider，OpenAI 兼容统一接口 |
| 终端 UI | rich / textual | 对话式引导交互 |
| 数据处理 | pandas + polars + duckdb | 覆盖 CSV/Excel/SQLite/Parquet |
| PPT 生成 | dashi-ppt-skill（通过 npx 调用） | 12 套主题、1020 版式、浏览器可编辑 + PPTX 导出 |
| 版本管理 | git | 项目级别自动初始化 |
| Web 搜索 | duckduckgo / AnySearch / z.ai | S4 阶段信息扩充，支持系统代理 |
| Web 读取 | Jina Reader (r.jina.ai) | 需要 API Key，支持系统代理 |
| 国际化 | 中文 / 英文 | 其他语言后续不考虑 |

---

## 2. 总体架构

### 2.1 架构模式：六阶段门控状态机

```
S1(选题) → S2(数据需求) → S3(数据加载) → S4(分析) → S5(报告) → S6(PPT)
  │            │               │              │            │          │
  └───── 用户门控 ──────────── 用户门控 ──── 用户门控 ─── 用户门控 ── 用户门控
```

每个阶段有四种状态：`pending` → `in_progress` → `awaiting_review` → `completed`。

### 2.2 模型分工

| 阶段 | 模型类型 | 推荐模型 | 核心任务 |
|------|---------|---------|---------|
| S1-S2 | **推理型** | DeepSeek-R1 / o1-mini | 高质量逻辑推导，结构化输出 |
| S3 | 无 LLM | — | 纯数据处理：加载、profile、验证 |
| S4 | **分析型** | GPT-4o / Claude 3.5 Sonnet | 长上下文 + 工具体系，迭代分析 |
| S5-S6 | **写作型** | Claude 3.5 Sonnet / DeepSeek-V3 | 文字组织与 dashi-ppt prompt 构造 |

用户可为每个角色独立配置模型，也允许三个角色使用同一模型。

### 2.3 组件分层

```
┌─────────────────────────────────┐
│          CLI Layer               │  ← rich prompt / 命令解析 / 交互
├─────────────────────────────────┤
│       Stage Orchestrator         │  ← 状态机引擎 / 门控逻辑
├──────────┬──────────┬───────────┤
│   S1-S2  │    S3    │  S4       │  ← 阶段模块
│  (推理)  │ (无LLM)  │ (分析)    │
├──────────┴──────────┴───────────┤
│       LLM Provider Layer         │  ← litellm 统一适配
├─────────────────────────────────┤
│         Tool Layer               │  ← Web Search / Jina Fetch / Code Exec
├─────────────────────────────────┤
│     I/O & Persistence Layer      │  ← YAML 状态 / MD 文档 / 数据文件
├─────────────────────────────────┤
│      dashi-ppt Bridge            │  ← subprocess: npx dashi-ppt-skill
├─────────────────────────────────┤
│      Auto Git Commit             │  ← 退出/产出/确认时自动提交
└─────────────────────────────────┘
```

---

## 3. 项目结构

### 3.1 工具自身结构（仓库）

```
AnaPPTAgent/
├── pyproject.toml              # uv 项目配置 + 依赖
├── README.md
├── src/
│   └── anappt/
│       ├── __init__.py
│       ├── cli.py              # 命令行入口
│       ├── orchestrator.py     # 状态机引擎
│       ├── stage_base.py       # 阶段基类
│       ├── stages/
│       │   ├── __init__.py
│       │   ├── s1_topic.py
│       │   ├── s2_data_req.py
│       │   ├── s3_data_load.py
│       │   ├── s4_analysis.py
│       │   ├── s5_report.py
│       │   └── s6_ppt.py
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── provider.py     # litellm 封装
│       │   └── models.py       # 模型配置模型
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── web_search.py
│       │   ├── web_fetch.py
│       │   └── code_exec.py    # Python 沙箱执行
│       ├── io/
│       │   ├── __init__.py
│       │   ├── config.py       # report.yaml 读写
│       │   ├── state.py        # state.yaml 读写
│       │   └── data_loader.py  # 多格式数据加载
│       └── bridge/
│           ├── __init__.py
│           └── dashi_ppt.py    # npx dashi-ppt-skill 桥接
├── templates/
│   └── project/                # new 命令的模板
│       ├── report.yaml.tmpl
│       ├── .gitignore.tmpl
│       └── data/
│           └── .gitkeep
└── tests/
    └── ...
```

### 3.2 分析项目目录结构（由 `anappt new` 创建）

```
my_data_report/
├── report.yaml                 # [S1产出] 报告选题配置
├── README.md                   # 项目说明（自动生成）
├── data/                       # [用户提供] 数据文件
│   ├── raw_data.csv
│   ├── user_events.db          # SQLite
│   └── README.md               # 埋点/表结构说明
├── output/                     # [S5-S6产出] 最终交付物
│   ├── final_report.md
│   ├── images/                 # 分析图表
│   └── presentation.html       # dashi-ppt HTML
│   └── presentation.pptx       # 导出 PPTX
└── .anappt/                    # Agent 内部状态
    ├── state.yaml              # 阶段状态机
    ├── session_history/        # 对话记录
    │   └── 2026-07-17.md
    ├── memory.md               # 项目记忆
    ├── s2_data_requirement.md  # [S2产出] 数据需求清单
    ├── s3_data_profile.md      # [S3产出] 数据概览报告
    └── s4_analysis_report.md   # [S4产出] 分析报告（可迭代多版）
```

---

## 4. 六阶段详细设计

### 4.1 S1 · 选题与目标定义

**目标**：将用户的口头描述转化为结构化的报告规格书。

**输入**：用户通过对话描述需求（自由文本）

**Agent 行为**：
1. 通过对话收集以下信息：
   - 报告选题（主题、背景、动机）
   - 报告目标受众（谁看这份报告？决策层/执行层/外部客户？）
   - 报告目标（要解决什么问题？要支撑什么决策？）
   - 交付形式（PPT 页数期望、是否需要 PDF 版等）
   - 成功标准（怎样的报告算"好"？）
   - 可选：周期标识（月度/季度/一次性）
2. 推理型模型整理为结构化 `report.yaml`
3. 展示给用户确认/修改

**产出**：

```yaml
# report.yaml
project:
  name: "2026年H1用户增长分析"
  type: "monthly"           # one_time | monthly | quarterly
  created: "2026-07-17"

report:
  topic: "用户增长趋势与渠道效率分析"
  motivation: "上半年DAU增长放缓，需评估各渠道拉新效率"
  audience:
    - "管理层"
    - "增长团队"
  objectives:
    - "识别增长瓶颈"
    - "评估渠道ROI"
    - "提出Q3增长策略建议"
  success_criteria:
    - "结论有数据支撑"
    - "建议可落地执行"

delivery:
  ppt_pages: "15-20"
  formats: ["pptx", "html"]
  theme_preference: null     # 由用户后续在 S6 选择
```

**门控条件**：用户确认 `report.yaml` 内容无误后，写入项目目录，S1 标记为 `completed`。

---

### 4.2 S2 · 数据需求分析

**目标**：基于报告选题，推导完成分析所需的数据清单。

**输入**：
- `report.yaml`
- 用户可选提供的埋点文档 / 数据库表结构说明（存放在 `data/` 下）

**Agent 行为**：
1. 读取 `report.yaml` 和 `data/` 下的说明文档
2. 推理型模型分析：要回答报告中的问题，需要哪些数据？
3. 生成数据需求清单，包含：
   - 指标名称与计算口径
   - 需要的维度拆分
   - 数据时间范围
   - 最低数据粒度
   - 预估数据量级
4. **不检查数据是否存在**——纯粹从分析需求出发

**产出**：`.anappt/s2_data_requirement.md`

```markdown
# 数据需求清单

## 1. 用户行为数据
- 指标：DAU、WAU、MAU
- 维度：日期、渠道、新老用户
- 时间范围：2026-01-01 至 2026-06-30
- 粒度：日级别
- 来源：埋点表 `user_events`

## 2. 渠道投放数据
- 指标：曝光量、点击量、下载量、激活量、付费金额
- 维度：日期、渠道名称、广告计划ID
- 时间范围：同上
- 来源：广告投放后台导出

## 3. 收入数据
- 指标：日收入、ARPU、LTV
- 维度：日期、用户注册渠道
- 时间范围：同上
- 来源：财务系统
```

**门控条件**：用户确认需求清单后，S2 标记为 `completed`。此时用户可以离开去准备数据。

---

### 4.3 S3 · 数据加载与验证

**目标**：加载用户提供的数据，检查质量与覆盖度。

**输入**：`data/` 目录下的数据文件

**Agent 行为**（无 LLM，纯数据处理）：
1. 扫描 `data/` 目录，自动识别文件格式
2. 使用 pandas/polars/duckdb 加载数据
3. 生成数据 profile：
   - 每个文件/表：行数、列数、列类型、空值率
   - 数值列：min/max/mean/median/std
   - 分类列：unique 值数量、top 值
   - 日期列：时间范围覆盖
4. 对照 S2 需求清单，检查覆盖度
5. 若覆盖率不足，提示用户补充数据，可回到 S2 调整需求

**产出**：`.anappt/s3_data_profile.md`

**门控条件**：用户确认数据就绪后，S3 标记为 `completed`。

---

### 4.4 S4 · 数据分析（核心阶段）

**目标**：基于数据进行深度分析，产出分析报告。

**这是整个流水线中最重要的阶段，支持迭代循环。**

**输入**：
- `report.yaml`（分析目标）
- `data/`（已加载验证的数据）
- `s2_data_requirement.md`（分析维度参考）

**Agent 行为（分析型模型 + 工具体系）**：

```
S4 迭代循环：
┌──────────────────────────────────────┐
│  1. Agent 加载数据上下文              │
│  2. LLM 进行初步分析推理             │
│  3. 按需调用工具：                    │
│     - Web Search: 补充行业背景      │
│     - Web Fetch: 读取相关报告/文章  │
│     - Code Exec: 数据计算/统计      │
│  4. 整合分析结论 → 输出分析报告草案  │
│  5. 用户复核 → 提供反馈             │
│  6. Agent 接收反馈 → 深度推理补充    │
│  7. 更新报告 → 再提交用户确认        │
│  8. 循环直到用户满意                 │
└──────────────────────────────────────┘
```

**工具体系**：

| 工具 | 功能 | 使用场景 |
|------|------|---------|
| `search_web(query)` | 搜索互联网信息 | 获取行业趋势、竞品数据、市场报告 |
| `fetch_url(url)` | 读取指定网页内容 | 阅读行业报告、新闻、政策文件 |
| `execute_python(code)` | 在隔离环境中执行 Python | 统计计算、数据透视、关联分析 |

**注意**：S4 不强制生成图表。分析报告以数据列表和文字结论为主，为后续 PPT 编辑留出灵活性。若用户要求图表，按需生成至 `output/images/`。

**产出**：`.anappt/s4_analysis_report.md`（可多次覆盖更新）

**门控条件**：用户明确确认"分析结论无误，可以进入报告撰写"后，S4 标记为 `completed`。

---

### 4.5 S5 · 报告生成

**目标**：将分析结论组织为完整、可交付的分析报告。

**输入**：
- `report.yaml`
- `s4_analysis_report.md`（已确认的分析结论）
- `output/images/`（可选图表）

**Agent 行为**：
1. 写作型模型读取所有上下文
2. 按标准报告结构生成：
   - 摘要 / Executive Summary
   - 背景与目标
   - 数据来源与方法
   - 核心发现（多章节）
   - 结论与建议
   - 附录 / 数据说明
3. 展示给用户确认/修改

**产出**：`output/final_report.md`

**门控条件**：
- S5 完成后，Agent 明确提醒用户打开 `output/final_report.md` 查看和修改
- 用户可以：
  - 直接用编辑器打开文件自行修改
  - 或直接跟 Agent 对话，提出修改意见，由 Agent 对报告进行优化
- 用户可以多次往返修改，直到满意为止
- 用户明确确认"报告内容无误"后，S5 标记为 `completed`，方可进入 S6

---

### 4.6 S6 · PPT 生成

**目标**：将 `output/final_report.md` 交给 dashi-ppt-skill，生成可编辑 PPT。

**输入**：`output/final_report.md`

**Agent 行为**：
1. 写作型模型读取报告，构造 dashi-ppt-skill 的 prompt：
   - 主题描述
   - 受众
   - 页数期望
   - 关键结论与数据点
2. 用户从 12 套主题中选择（Agent 展示预览）
3. 用户确认是否需要配图（图片/视频）
4. 调用 `npx dashi-ppt-skill@latest` 生成 HTML
5. 用户在浏览器中编辑确认后，导出 PPTX/PDF

**dashi-ppt-skill 集成方式**：
```
AnaPPTAgent                              dashi-ppt-skill
   │                                          │
   │  1. 构造 prompt（主题+受众+结论）        │
   │  2. 用户选主题                           │
   │  3. 触发生成 ──────────────────────────→ │
   │                                          │ 4. npx 安装/更新依赖
   │                                          │ 5. AI 自动组稿排版
   │                                          │ 6. 输出 HTML
   │  7. 取回 output/presentation.html ←──────│
   │  8. 用户在浏览器编辑                     │
   │  9. 用户确认后触发导出 ─────────────────→ │
   │                                          │ 10. npm run export:pptx
   │  11. 取回 output/presentation.pptx ←─────│
```

**桥接层实现**：
- 通过 `subprocess` 执行 npm/npx 命令
- dashi-ppt-skill 项目目录存放在项目的 `.anappt/dashi-ppt-project/` 下
- 导出命令通过 `npm --prefix <目录> run export:pptx` 调用

**产出**：
- `output/presentation.html`（可编辑 HTML）
- `output/presentation.pptx`（导出 PPTX）

**门控条件**：用户确认 PPT 最终效果后，S6 标记为 `completed`，整个流水线完成。

---

## 5. 状态机设计

### 5.1 状态文件结构

```yaml
# .anappt/state.yaml
project_name: "2026年H1用户增长分析"
created_at: "2026-07-17T14:00:00+08:00"
updated_at: "2026-07-17T14:30:00+08:00"
current_stage: "S4"

stages:
  - id: "S1"
    name: "选题与目标定义"
    status: "completed"
    started_at: "2026-07-17T14:00:00"
    completed_at: "2026-07-17T14:10:00"

  - id: "S2"
    name: "数据需求分析"
    status: "completed"
    started_at: "2026-07-17T14:10:00"
    completed_at: "2026-07-17T14:20:00"

  - id: "S3"
    name: "数据加载与验证"
    status: "completed"
    started_at: "2026-07-17T14:20:00"
    completed_at: "2026-07-17T14:30:00"

  - id: "S4"
    name: "数据分析"
    status: "awaiting_review"
    started_at: "2026-07-17T14:30:00"
    iteration: 2              # 当前迭代轮次

  - id: "S5"
    name: "报告生成"
    status: "pending"

  - id: "S6"
    name: "PPT 生成"
    status: "pending"
```

### 5.2 状态转换规则

| 当前状态 | 允许的操作 | 目标状态 |
|---------|-----------|---------|
| `pending` | `anappt run` 启动阶段 | `in_progress` |
| `in_progress` | Agent 完成产出 | `awaiting_review` |
| `awaiting_review` | 用户 `confirm` | `completed`（解锁下一阶段） |
| `awaiting_review` | 用户 `revise`（提供反馈） | `in_progress`（重新处理） |
| `completed` | — | 不可回退（通过 git 追溯历史） |

---

## 6. CLI 命令设计

### 6.1 命令清单

| 命令 | 功能 |
|------|------|
| `anappt new <name>` | 在当前目录创建新的分析项目 |
| `anappt run` | 恢复/继续当前项目（自动从 `current_stage` 开始） |
| `anappt status` | 查看当前项目各阶段状态 |
| `anappt run --stage S4` | 从指定阶段开始（需前置阶段已完成） |
| `anappt run --from-scratch` | 忽略已有状态，重新开始 |
| `anappt config` | 配置 LLM 模型（交互式） |
| `anappt config show` | 显示当前 LLM 配置 |

### 6.2 交互流程示例

```
$ anappt new Q3渠道分析
  ✓ 项目已创建：./Q3渠道分析/
  ✓ Git 仓库已初始化
  ✓ 编辑 ./Q3渠道分析/report.yaml 配置报告信息
  ✓ 将数据文件放入 ./Q3渠道分析/data/
  ✓ 运行 anappt run 开始

$ cd Q3渠道分析

$ anappt run
  [S1] 选题与目标定义 (推理型模型: deepseek-r1)
  请描述你的报告需求...
  > 我想分析Q3各渠道的ROI，对比SEM和信息流的效率，给增长团队一个优化建议

  Agent: 我理解你的需求。让我确认几点：
  1. 时间范围是 2026年Q3（7-9月）吗？
  2. 受众是增长团队 + 管理层？
  3. 重点放在 SEM vs 信息流的 ROI 对比？

  ... (确认后生成 report.yaml)

  [✓] S1 完成。report.yaml 已生成，请确认：
      - 报告选题：Q3渠道ROI对比分析
      - 受众：增长团队、管理层
      - 目标：优化渠道投放策略
  输入 confirm 确认 或 描述修改意见 >

  ... (用户确认后，自动进入 S2)
```

---

## 7. LLM Provider 设计

### 7.1 基于 litellm 的统一抽象

```python
# provider.py 设计思路
class AnaPPTLLM:
    """litellm 的薄封装，支持角色-模型映射"""

    def __init__(self, config: ModelConfig):
        self.reasoning_model = config.reasoning   # S1-S2
        self.analysis_model = config.analysis     # S4
        self.writing_model = config.writing       # S5-S6

    def chat(self, role: str, messages: list, **kwargs):
        """根据 role 选择对应模型，透传 litellm"""
        model = self._model_for_role(role)
        return litellm.completion(model=model, messages=messages, **kwargs)
```

### 7.2 模型配置（全局 / 项目级）

```yaml
# ~/.anappt/models.yaml （全局默认）
reasoning:
  provider: "deepseek"
  model: "deepseek-reasoner"
  api_base: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_API_KEY}"

analysis:
  provider: "openai"
  model: "gpt-4o"
  api_key: "${OPENAI_API_KEY}"

writing:
  provider: "anthropic"
  model: "claude-sonnet-4-20250514"
  api_key: "${ANTHROPIC_API_KEY}"
```

项目级 `report.yaml` 可以覆盖全局配置，允许用户对不同项目使用不同模型。

### 7.3 支持的 Provider

通过 litellm，天然支持：
- OpenAI / Azure OpenAI
- Anthropic (Claude)
- Google (Gemini)
- DeepSeek
- 智谱 (GLM)
- 月之暗面 (Moonshot)
- 阿里 (Qwen)
- Ollama（本地模型）
- vLLM / LM Studio
- 以及任何 OpenAI-compatible API

---

## 8. 工具层设计

### 8.1 Web Search

```
search_web(query: str, num_results: int = 5) → list[SearchResult]
```

支持三种后端，按优先级自动选择（配置了 API Key 的优先使用）：

| 后端 | 配置要求 | 说明 |
|------|---------|------|
| **duckduckgo-search**（默认） | 无需配置 | 免费、无需 API Key，通过 duckduckgo-search 库调用 |
| **AnySearch API** | 需配置 `ANYSEARCH_API_KEY` | 调用 https://www.anysearch.com/docs#search-api |
| **z.ai search tool** | 需配置 `ZAI_API_KEY` | 调用智谱搜索工具 API https://docs.bigmodel.cn |

后端选择逻辑：
1. 若配置了 `ANYSEARCH_API_KEY` → 使用 AnySearch
2. 若配置了 `ZAI_API_KEY` → 使用 z.ai
3. 若两者都配置了 → 按 `WEB_SEARCH_BACKEND` 环境变量指定（值：`anysearch` 或 `zai`）
4. 均未配置 → 回退到 duckduckgo-search

所有搜索后端均需自动识别系统代理（`HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 环境变量），以确保数据正确读取。

### 8.2 Web Fetch

```
fetch_url(url: str) → str
```

使用 Jina Reader API 进行网页内容读取：

- **API 端点**：`https://r.jina.ai/{url}`
- **认证**：通过 `JINA_API_KEY` 环境变量配置，请求头 `Authorization: Bearer <key>`
- **限制**：未配置 `JINA_API_KEY` 时，**不提供 Web Fetch 能力**，Agent 在 S4 阶段告知用户该功能不可用
- **代理支持**：自动识别系统代理（`HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`），使用 httpx 的 `trust_env=True` 配置

### 8.3 Code Execution（Python 沙箱）

```
execute_python(code: str, timeout: int = 60) → ExecutionResult
```

- 在隔离的 subprocess 中执行
- 限制：不允许网络访问、文件系统仅限 `data/` 和临时目录
- 超时控制
- 返回 stdout + stderr + 返回值

---

## 9. dashi-ppt-skill 桥接层

### 9.1 前置条件检查

```
1. 检查 Node.js >= 20（运行 `node --version`）
2. 检查 npm（运行 `npm --version`）
3. 检查 Chrome/Chromium/Edge 可用（PPTX 导出需要，`CHROME_PATH` 环境变量）
```

### 9.2 调用流程

```python
class DashiPPTBridge:
    def __init__(self, project_dir: Path):
        self.skill_dir = project_dir / ".anappt" / "dashi-ppt-project"

    def install_or_update(self) -> None:
        """npx dashi-ppt-skill@latest -- 安装/更新"""
        subprocess.run(["npx", "dashi-ppt-skill@latest"], cwd=self.skill_dir.parent)

    def generate(self, prompt: str, theme: str) -> Path:
        """触发 PPT 生成，返回 HTML 路径"""
        # 将 prompt 写入 dashi-ppt-skill 项目的上下文
        # 通过 npx 或直接调用 skill 的生成逻辑
        # 返回 output/presentation.html

    def export(self, format: str) -> Path:
        """导出 PPTX 或 PDF"""
        if format == "pptx":
            subprocess.run(
                ["npm", "--prefix", str(self.skill_dir), "run", "export:pptx",
                 "--", str(self.output_dir / "presentation.pptx")],
            )
        elif format == "pdf":
            subprocess.run(
                ["npm", "--prefix", str(self.skill_dir), "run", "export:pdf",
                 "--", str(self.output_dir / "presentation")],
            )
```

### 9.3 Prompt 构造策略

AnaPPTAgent 使用写作型模型，将 `final_report.md` 转换为 dashi-ppt-skill 的标准 prompt 格式：

1. 报告主题与目标受众
2. 希望突出的核心结论（3-5 个关键信息）
3. 推荐的页面结构
4. 数据要点（关键数字、趋势描述）
5. 风格偏好（正式/活泼/简洁等，由用户确认）

---

## 10. 迭代与反馈循环

### 10.1 S4 分析迭代

S4 是唯一支持多轮迭代的阶段：

```
分析型模型生成初始分析
        │
        ▼
   用户复核
   ├── 满意 → 确认完成
   ├── 部分不满 → 提供具体反馈（"这个结论依据不足，请补充XX数据佐证"）
   └── 完全重来 → 调整分析方向
        │
        ▼
   Agent 接收反馈
   ├── 搜索补充信息
   ├── 执行额外数据计算
   └── 深度推理补充
        │
        ▼
   更新分析报告 → 再次提交用户复核
```

### 10.2 门控不可跳过

所有阶段的门控都是强制性的。`--auto-confirm` 等跳过确认的参数**不提供**，这是有意为之的设计约束——确保人工把关在关键节点上的可靠性。

---

## 11. 非功能需求

### 11.1 安全性

- Code Execution 在隔离 subprocess 中运行，限制文件系统访问
- API Key 通过环境变量注入，不在 `report.yaml` 中明文存储
- 项目目录内容不自动上传（dashi-ppt-skill 在本地运行）

### 11.2 离线能力

- 使用本地 LLM（Ollama）时，S1-S6 全部离线可运行
- dashi-ppt-skill 生成的 HTML 离线可用
- Web Search 工具需要网络，可配置关闭

### 11.3 可扩展性

- 新阶段可通过继承 `StageBase` 添加
- 新工具可通过注册函数加入 S4 的工具体系
- 新 LLM provider 通过 litellm 自动获得支持

### 11.4 自动 Git 提交

为保证信息可追溯，Agent 在以下三个时机自动执行 `git add` + `git commit`：

| 触发点 | 触发时机 | commit message 格式 |
|--------|---------|-------------------|
| **用户退出** | Agent 进程正常退出前（Ctrl+C 或 `exit` 命令） | `chore: auto-save on exit` |
| **内容生成完成** | 每个阶段的 Agent 产出物写入磁盘后 | `feat(S{n}): complete {stage_name} — {产出文件名}` |
| **用户确认文件** | 用户执行 `confirm` 命令确认阶段产出后 | `feat(S{n}): confirm {stage_name}` |

commit message 遵循 Conventional Commits 规范，使用英文编写以保证工具链兼容性。

**注意**：`git add` 仅添加项目目录内的文件（排除 `.anappt/session_history/` 等高频临时文件）。若项目未初始化 git 仓库，自动跳过（无报错）。

---

## 12. 尚未决定的开放项

| # | 开放项 | 建议 | 待讨论 |
|---|--------|------|--------|
| 1 | 图表自动生成策略 | 当前 S4 不强制生成图表，按需手动触发 | 后续评估 |

---

## 附录 A：术语表

| 术语 | 定义 |
|------|------|
| 门控 (Gate) | 每个阶段末尾的强制用户确认节点 |
| 推理型模型 | 擅长逻辑推导和结构化输出的 LLM |
| 分析型模型 | 擅长长上下文理解和工具调用的 LLM |
| 写作型模型 | 擅长文字组织和内容表述的 LLM |
| 项目目录 | 一个分析报告的完整工作空间 |
| dashi-ppt-skill | 第三方 AI-agent skill，生成浏览器可编辑的 PPT，支持导出 PPTX/PDF |

---

## 附录 B：变更记录

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-07-17 | 初始版本 (v1.0) | AI 编程方法论专家 |
| 2026-07-17 | 修订 (v1.1)：细化 Web Search/Fetch 后端、S5 门控行为、自动 Git 提交、i18n 范围 | AI 编程方法论专家 |

---

> **下一步**：此规格文档完成自审后，将提交人类复核。复核通过后，进入实现计划编排阶段。
