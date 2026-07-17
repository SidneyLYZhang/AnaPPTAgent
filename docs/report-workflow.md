# 分析报告生成流程 / Analysis Report Generation Workflow

---

## 中文

### 概述

分析报告的生成经过 S1 到 S5 共五个阶段。每个阶段使用不同角色的 LLM 模型，产出特定的文档产物，并在阶段间设置人工审核门控。

### 流程图

```
report.yaml
     │
     ▼
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│   S1    │────▶│   S2    │────▶│   S3    │────▶│   S4    │────▶│   S5    │
│  选题    │     │ 数据需求 │     │ 数据加载 │     │ 数据分析 │     │ 报告生成 │
│reasoning│     │reasoning│     │  无LLM  │     │analysis │     │ writing │
└─────────┘     └─────────┘     └─────────┘     └─────────┘     └─────────┘
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
 s1_topic.md  s2_data_req.md  s3_data_profile.md  s4_analysis.md  output/report.md
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
  [审核门控]      [审核门控]      [审核门控]       [审核门控]       [审核门控]
  confirm/revise  confirm/revise  confirm/revise  confirm/revise  confirm/revise
```

### S1: 选题与目标定义

**模型角色**：reasoning（推理型）

**输入**：`report.yaml` 中的项目配置
- `project.name` — 项目名称
- `report.topic` — 分析选题
- `report.motivation` — 分析动机
- `report.audience` — 目标受众
- `report.objectives` — 分析目标
- `report.success_criteria` — 成功标准

**处理过程**：
1. 读取 `report.yaml` 配置
2. 构建 system prompt，要求 LLM 作为专业分析师
3. LLM 生成结构化的选题文档，包含：
   - 精炼选题（Refined Topic）
   - 分析目标（Analysis Objectives）
   - 成功标准（Success Criteria）
   - 建议方法（Suggested Approach）

**输出产物**：`.anappt/s1_topic.md`

**审核要点**：
- 选题方向是否准确
- 分析目标是否清晰可执行
- 建议方法是否合理

### S2: 数据需求分析

**模型角色**：reasoning（推理型）

**输入**：S1 产物 + `data/` 目录中已有的数据文件列表

**处理过程**：
1. 读取 S1 的选题文档
2. 扫描 `data/` 目录，获取已有文件列表
3. LLM 生成数据需求文档，包含：
   - 所需数据表（Required Data Tables）
   - 每个表的预期 Schema（列名、类型、描述）
   - 数据质量要求（Data Quality Requirements）
   - 建议数据源（Suggested Data Sources）

**输出产物**：`.anappt/s2_data_requirement.md`

**审核要点**：
- 数据需求是否合理覆盖分析目标
- 是否有遗漏的关键数据
- 用户在此阶段可以准备并放入数据文件到 `data/` 目录

> **重要**：这是用户准备数据的关键时机。审核 S2 后，用户应将所需的数据文件（CSV、Excel、SQLite、DuckDB、Parquet）放入 `data/` 目录，然后确认进入 S3。

### S3: 数据加载与验证

**模型角色**：无（不使用 LLM）

**输入**：`data/` 目录中的数据文件

**支持的数据格式**：
| 格式 | 扩展名 | 加载方式 |
|------|--------|----------|
| CSV | `.csv` | pandas |
| Excel | `.xlsx` | openpyxl + pandas |
| SQLite | `.db`, `.sqlite` | sqlite3 |
| DuckDB | `.duckdb` | duckdb |
| Parquet | `.parquet` | pyarrow |

**处理过程**：
1. 检测 `data/` 目录中所有支持的文件
2. 加载所有数据文件为 DataFrame
3. 生成数据档案（Data Profile），包含：
   - 文件总数
   - 每个数据表的形状（行数 x 列数）
   - 列名列表
   - 数据类型
   - 数值列的统计摘要（count, mean, std, min, max 等）
   - 空值统计
   - 文件详情（格式、大小）

**输出产物**：`.anappt/s3_data_profile.md`

**审核要点**：
- 数据是否完整加载
- 列名和数据类型是否正确
- 是否有大量空值需要处理
- 数据量是否满足分析需求

### S4: 数据分析

**模型角色**：analysis（分析型）

**输入**：S1 选题文档 + S2 数据需求 + S3 数据档案 + `data/` 目录中的数据

**处理过程**：
1. 读取 S1、S2 产物作为上下文
2. 加载 `data/` 目录中的所有数据文件
3. 生成数据信息 JSON（`.anappt/data_info.json`），包含每个表的行数、列数、列名、数据类型
4. 构建工具集（3 个工具）：

| 工具 | 功能 | 限制 |
|------|------|------|
| `execute_python` | 执行 Python 代码 | 沙箱隔离：网络封锁、文件系统受限、60 秒超时 |
| `search_web` | Web 搜索 | 自动选择后端：DuckDuckGo / AnySearch / z.ai |
| `fetch_url` | 读取网页内容 | 仅当 `JINA_API_KEY` 已配置时可用 |

5. 创建 AgentLoop（最多 10 次迭代）
6. LLM 通过 ReAct 模式执行分析：
   - 加载和探索数据
   - 执行统计分析
   - 创建可视化（如需要）
   - 识别关键洞察和模式
7. 生成分析报告，包含：
   - 执行摘要（Executive Summary）
   - 方法论（Methodology）
   - 关键发现（Key Findings）
   - 详细分析（Detailed Analysis）
   - 建议（Recommendations）

**输出产物**：`.anappt/s4_analysis_report.md`

**审核要点**：
- 分析是否覆盖了所有目标
- 统计方法是否合理
- 关键发现是否有数据支撑
- 建议是否可执行

> **沙箱安全说明**：代码在隔离的子进程中执行，网络访问被完全封锁（socket 模块被替换），文件系统访问限制在 `data/` 目录、临时目录和当前工作目录。

### S5: 报告生成

**模型角色**：writing（写作型）

**输入**：S4 分析报告 + S1 选题文档 + `report.yaml` 配置

**处理过程**：
1. 读取 S4 分析报告
2. 读取 S1 选题文档作为上下文
3. 读取 `report.yaml` 中的受众和目标
4. LLM 将原始分析转化为精炼报告：
   - 使用规范的 Markdown 格式（标题、表格、列表）
   - 包含：执行摘要、背景、方法论、发现、结论、建议
   - 语言与项目配置一致

**输出产物**：
- `output/report.md` — 最终报告（用户可查看和编辑）
- `.anappt/s5_report.md` — 报告副本（内部存档）

**审核要点**：
- 报告结构是否清晰
- 语言是否适合目标受众
- 结论是否有数据支撑
- 建议是否具体可执行

> **重要**：S5 完成后，系统会提示用户打开报告文件查看和修改。用户可以：
> 1. 直接编辑 `output/report.md` 文件
> 2. 在终端中描述修改意见，让 LLM 重新生成
> 3. 确认后进入 S6（PPT 生成）

### 阶段间审核机制

每个阶段完成后，状态变为 `awaiting_review`，用户可以：

1. **确认（confirm）**：接受当前输出，进入下一阶段
   - 触发 Git 提交：`feat(S1): confirm 选题与目标定义`

2. **修改（revise）**：提供修改意见，重新运行当前阶段
   - 阶段迭代次数 +1
   - 触发 Git 提交：`feat(S1): complete 选题与目标定义 - .anappt/s1_topic.md`
   - 修改意见被记录到会话日志

3. **退出（exit）**：保存当前进度并退出
   - 触发 Git 提交：`chore: auto-save on exit`
   - 下次可用 `anappt resume` 继续

### 产物文件一览

| 阶段 | 产物文件 | 说明 |
|------|---------|------|
| S1 | `.anappt/s1_topic.md` | 选题与目标文档 |
| S2 | `.anappt/s2_data_requirement.md` | 数据需求文档 |
| S3 | `.anappt/s3_data_profile.md` | 数据档案 |
| S4 | `.anappt/s4_analysis_report.md` | 分析报告 |
| S4 | `.anappt/data_info.json` | 数据结构信息（JSON） |
| S5 | `output/report.md` | 最终分析报告 |
| S5 | `.anappt/s5_report.md` | 报告副本 |

---

## English

### Overview

The analysis report is generated through five stages (S1-S5). Each stage uses a different LLM model role, produces specific artifacts, and includes a human review gate between stages.

### Flow Diagram

```
report.yaml
     │
     ▼
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│   S1    │────▶│   S2    │────▶│   S3    │────▶│   S4    │────▶│   S5    │
│  Topic  │     │  Data   │     │  Data   │     │  Data   │     │ Report  │
│reasoning│     │reasoning│     │  No LLM │     │analysis │     │ writing │
└─────────┘     └─────────┘     └─────────┘     └─────────┘     └─────────┘
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
 s1_topic.md  s2_data_req.md  s3_data_profile.md  s4_analysis.md  output/report.md
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
 [Review Gate]  [Review Gate]  [Review Gate]   [Review Gate]   [Review Gate]
 confirm/revise confirm/revise confirm/revise  confirm/revise  confirm/revise
```

### S1: Topic & Goal Definition

**Model Role**: reasoning

**Input**: Project configuration from `report.yaml`
- `project.name`, `report.topic`, `report.motivation`
- `report.audience`, `report.objectives`, `report.success_criteria`

**Process**:
1. Reads `report.yaml` configuration
2. LLM acts as an expert analyst to generate a structured topic document with:
   - Refined Topic
   - Analysis Objectives
   - Success Criteria
   - Suggested Approach

**Output**: `.anappt/s1_topic.md`

**Review Focus**: Topic direction accuracy, objective clarity, approach feasibility

### S2: Data Requirement Analysis

**Model Role**: reasoning

**Input**: S1 output + existing data files in `data/`

**Process**:
1. Reads S1 topic document
2. Scans `data/` directory for existing files
3. LLM generates data requirement document with:
   - Required Data Tables
   - Expected Schema (column name, type, description)
   - Data Quality Requirements
   - Suggested Data Sources

**Output**: `.anappt/s2_data_requirement.md`

> **Important**: This is the key moment for users to prepare data. After reviewing S2, users should place data files (CSV, Excel, SQLite, DuckDB, Parquet) into the `data/` directory, then confirm to proceed to S3.

### S3: Data Loading & Validation

**Model Role**: None (no LLM used)

**Input**: Data files in `data/` directory

**Supported Formats**:
| Format | Extension | Loader |
|--------|-----------|--------|
| CSV | `.csv` | pandas |
| Excel | `.xlsx` | openpyxl + pandas |
| SQLite | `.db`, `.sqlite` | sqlite3 |
| DuckDB | `.duckdb` | duckdb |
| Parquet | `.parquet` | pyarrow |

**Process**:
1. Detects all supported files in `data/`
2. Loads all files as DataFrames
3. Generates data profile:
   - Total file count
   - Shape (rows x columns) per table
   - Column names and data types
   - Statistics for numeric columns
   - Null counts
   - File details (format, size)

**Output**: `.anappt/s3_data_profile.md`

### S4: Data Analysis

**Model Role**: analysis

**Input**: S1 topic + S2 requirements + S3 profile + data files

**Process**:
1. Reads S1, S2 outputs as context
2. Loads all data files
3. Generates data info JSON (`.anappt/data_info.json`)
4. Builds toolset (3 tools):

| Tool | Function | Limitations |
|------|----------|-------------|
| `execute_python` | Execute Python code | Sandboxed: network blocked, FS restricted, 60s timeout |
| `search_web` | Web search | Auto-selects backend: DuckDuckGo / AnySearch / z.ai |
| `fetch_url` | Read web pages | Only available when `JINA_API_KEY` is set |

5. Creates AgentLoop (max 10 iterations)
6. LLM performs analysis via ReAct pattern:
   - Load and explore data
   - Perform statistical analysis
   - Create visualizations if needed
   - Identify key insights and patterns
7. Generates analysis report with: Executive Summary, Methodology, Key Findings, Detailed Analysis, Recommendations

**Output**: `.anappt/s4_analysis_report.md`

> **Sandbox Security**: Code runs in an isolated subprocess with network access fully blocked (socket module replaced) and file system access restricted to `data/`, temp directory, and current working directory.

### S5: Report Generation

**Model Role**: writing

**Input**: S4 analysis report + S1 topic + `report.yaml` config

**Process**:
1. Reads S4 analysis report
2. Reads S1 topic for context
3. Reads audience and objectives from config
4. LLM transforms raw analysis into polished report with proper Markdown formatting

**Output**:
- `output/report.md` — Final report (user can view and edit)
- `.anappt/s5_report.md` — Report copy (internal archive)

> **Important**: After S5, the system prompts the user to open and review the report. Users can:
> 1. Directly edit `output/report.md`
> 2. Describe revision feedback in the terminal for LLM to regenerate
> 3. Confirm to proceed to S6 (PPT generation)

### Review Gate Mechanism

After each stage completes, status becomes `awaiting_review`. Users can:

1. **Confirm**: Accept output, advance to next stage
   - Triggers Git commit: `feat(S1): confirm Topic Definition`

2. **Revise**: Provide feedback to re-run the stage
   - Iteration count +1
   - Triggers Git commit: `feat(S1): complete Topic Definition - .anappt/s1_topic.md`
   - Feedback logged to session history

3. **Exit**: Save progress and exit
   - Triggers Git commit: `chore: auto-save on exit`
   - Resume later with `anappt resume`

### Artifact Files Summary

| Stage | Artifact | Description |
|-------|----------|-------------|
| S1 | `.anappt/s1_topic.md` | Topic & goal document |
| S2 | `.anappt/s2_data_requirement.md` | Data requirement document |
| S3 | `.anappt/s3_data_profile.md` | Data profile |
| S4 | `.anappt/s4_analysis_report.md` | Analysis report |
| S4 | `.anappt/data_info.json` | Data structure info (JSON) |
| S5 | `output/report.md` | Final analysis report |
| S5 | `.anappt/s5_report.md` | Report copy |
