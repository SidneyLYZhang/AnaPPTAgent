# 分析报告生成流程

### 概述

分析报告的生成经过 S1 到 S5 共五个阶段，由 `ConversationRunner` 驱动的对话式 TUI 串接。每个阶段使用不同角色的 LLM 模型，通过对话生成特定产物，并在阶段间设置人工审核门控（`/confirm`）。S6（PPT 生成）见 `ppt-workflow.md`，不在本文档范围。

### 流程图

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│   S1    │────▶│   S2    │────▶│   S3    │────▶│   S4    │────▶│   S5    │
│  选题    │     │ 数据需求 │     │ 数据加载 │     │ 数据分析 │     │ 报告生成 │
│reasoning│     │reasoning│     │reasoning│     │analysis │     │ writing │
└─────────┘     └─────────┘     └─────────┘     └─────────┘     └─────────┘
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
 report.yaml   s2_data_req.md  s3_data_profile.md  s4_analysis.md  output/final_report.md
 + s1_topic.md
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
  [审核门控]      [审核门控]      [审核门控]       [审核门控]       [审核门控]
   /confirm        /confirm        /confirm         /confirm         /confirm
```

### S1: 选题与目标定义

**模型角色**：reasoning（推理型）

**对话目标**：通过对话收集选题/动机/受众/目标/成功标准/交付形式，生成 `report.yaml`（项目根）+ `.anappt/s1_topic.md`

**处理过程**：
1. 通过对话依次收集：
   - 报告选题与动机（背景、要解决的业务问题）
   - 目标受众（决策层/执行层/外部客户等，可多个）
   - 报告目标（要支撑的决策、要回答的具体问题）
   - 成功标准（怎样的报告算「好」）
   - 交付形式（期望 PPT 页数、是否需要 PDF/HTML、主题偏好）
2. 调用 `write_artifact("report.yaml", <YAML>)` 写入项目根目录的 `report.yaml`，YAML 结构含 `project`/`report`/`delivery` 三段
3. 调用 `write_artifact(".anappt/s1_topic.md", <内容>)` 写入细化选题文档，对选题背景、动机、目标受众、报告目标、成功标准、建议分析思路做更详尽的展开
4. 提示用户通读两份产物，确认无误后输入 `/confirm` 推进；用户也可直接在对话中提出修改意见，由 LLM 更新后再等待 `/confirm`

**输出产物**：
- `report.yaml` — 项目根目录的报告规格书
- `.anappt/s1_topic.md` — 细化选题文档（供 S2/S4 引用）

**工具子集**：`read_file`/`write_artifact`/`read_memory`/`read_history`

**is_ready 校验**：
- `report.yaml` 存在且可被 `ReportConfig.from_yaml` 解析
- `report.topic`、`report.motivation`、`report.objectives` 三个关键字段非空
- `.anappt/s1_topic.md` 存在

**审核要点**：
- 选题方向是否准确
- 分析目标是否清晰可执行
- 建议方法是否合理

### S2: 数据需求分析

**模型角色**：reasoning（推理型）

**对话目标**：基于 `report.yaml` 与数据文件推导完成分析所需的数据需求清单，生成 `.anappt/s2_data_requirement.md`

**输入**：S1 产物（`report.yaml` + `.anappt/s1_topic.md`）+ `data/` 目录中已有的数据文件列表与说明文档（可选）

**处理过程**：
1. 用 `read_file` 读取 `report.yaml` 与 `.anappt/s1_topic.md` 作为推导依据
2. 如 `data/` 下存在用户提供的埋点文档、表结构说明、数据字典（如 `data/README.md`、`data/schema.md`），用 `read_file` 读取作为参考；不存在则纯从分析需求出发推导
3. LLM 推导数据需求清单，每项至少包含：
   - 指标名称与计算口径
   - 需要的维度拆分
   - 数据时间范围
   - 最低数据粒度
   - 预估数据量级
   - 数据来源
4. 调用 `write_artifact(".anappt/s2_data_requirement.md", <内容>)` 写入清单
5. 提示用户通读产物，确认无误后输入 `/confirm`；如需修改可在对话中提出

> **重要**：这是用户准备数据的关键时机。审核 S2 后，用户应将所需的数据文件（CSV、Excel、SQLite、DuckDB、Parquet）放入 `data/` 目录，然后确认进入 S3。

**输出产物**：`.anappt/s2_data_requirement.md`

**工具子集**：`read_file`/`write_artifact`/`read_memory`/`read_history`

**is_ready 校验**：`.anappt/s2_data_requirement.md` 存在且包含至少一个 Markdown 标题或列表项

**审核要点**：
- 数据需求是否合理覆盖分析目标
- 是否有遗漏的关键数据
- 用户在此阶段可以准备并放入数据文件到 `data/` 目录

### S3: 数据加载与验证

**模型角色**：reasoning（对话式路径由 LLM 驱动，编排 `execute_python` 调用完成数据扫描与 profile 生成；遗留 `run()` 为纯本地处理，已不在活动路径中）

**输入**：`data/` 目录中的数据文件

**支持的数据格式**：
| 格式 | 扩展名 | 加载方式 |
|------|--------|----------|
| CSV | `.csv` | pandas |
| Excel | `.xlsx`, `.xls` | openpyxl + pandas |
| SQLite | `.db`, `.sqlite`, `.sqlite3` | sqlite3 |
| DuckDB | `.duckdb` | duckdb |
| Parquet | `.parquet` | pyarrow |

**处理过程**：
1. 检测 `data/` 目录中所有支持的文件（共 8 种扩展名）
2. 加载所有数据文件为 DataFrame
3. 生成数据档案（Data Profile），包含：
   - 文件总数
   - 每个数据表的形状（行数 x 列数）
   - 列名列表与数据类型
   - 数值列的统计摘要（count, mean, std, min, max 等）
   - 空值统计
   - 文件详情（格式、大小）
4. 对照 S2 数据需求清单检查覆盖度
5. 写入 `.anappt/s3_data_profile.md`

**输出产物**：`.anappt/s3_data_profile.md`

**is_ready 校验**：`.anappt/s3_data_profile.md` 存在且非空

**审核要点**：
- 数据是否完整加载
- 列名和数据类型是否正确
- 是否有大量空值需要处理
- 数据量是否满足分析需求

### S4: 数据分析

**模型角色**：analysis（分析型）

**对话目标**：基于数据进行迭代式深度分析，产出 `.anappt/s4_analysis_report.md`，支持用户多轮反馈

**输入**：`report.yaml` + `data/` 数据文件 + `.anappt/s2_data_requirement.md` + `.anappt/s3_data_profile.md`（若已生成）

**处理过程**：
1. 用 `read_file` 读取上下文：`report.yaml`、`data/` 下的数据文件与说明文档、S2 需求清单、S3 数据 profile
2. 进行初步分析推理，形成第一版结论草案
3. 按需调用工具进行迭代补充（可多轮）：
   - `execute_python`：统计计算、数据透视、关联分析，按需生成图表至 `output/images/`
   - `search_web`：补充行业背景、竞品数据、市场报告
   - `fetch_url`：读取相关网页/报告/政策文件全文（若 `JINA_API_KEY` 未配置则改用 `search_web` 摘要）
4. 整合分析结论，调用 `write_artifact(".anappt/s4_analysis_report.md", <内容>)` 写入草案，使用清晰的 Markdown 结构（执行摘要、方法、关键发现、详细分析、建议等章节）
5. 提示用户复核草案并提供反馈；接收反馈 → 深度推理补充 → 更新报告 → 再次提交用户确认
6. 循环直到用户输入 `/confirm` 推进至 S5

**输出产物**：`.anappt/s4_analysis_report.md`（对话路径不生成 `.anappt/data_info.json`）

**工具子集**：`read_file`/`write_artifact`/`execute_python`/`search_web`/`fetch_url`/`read_memory`/`read_history`

**is_ready 校验**：`.anappt/s4_analysis_report.md` 存在且非空

**审核要点**：
- 分析是否覆盖了所有目标
- 统计方法是否合理
- 关键发现是否有数据支撑
- 建议是否可执行

> **沙箱安全说明**：`execute_python` 在隔离的子进程中执行，网络访问被完全封锁（socket 模块被替换），文件系统访问限制在 `data/` 目录、临时目录和当前工作目录。

### S5: 报告生成

**模型角色**：writing（写作型）

**对话目标**：将分析结论组织为完整、可交付的分析报告，产出 `output/final_report.md`

**输入**：`report.yaml` + `.anappt/s4_analysis_report.md` + 可选 `output/images/`

**处理过程**：
1. 用 `read_file` 读取上下文：`report.yaml`（选题、受众、目标、成功标准）、`.anappt/s4_analysis_report.md`（已确认的分析结论）、`output/images/` 下的图表文件清单（可选）
2. 按标准报告结构生成完整报告，至少包含以下章节：
   - 摘要 / Executive Summary
   - 背景与目标
   - 数据来源与方法
   - 核心发现（可按主题拆为多个子章节）
   - 结论与建议
   - 附录 / 数据说明
3. 调用 `write_artifact("output/final_report.md", <内容>)` 写入报告，使用清晰的 Markdown 格式（标题、表格、列表、图片引用等）
4. 写完后**明确提醒用户打开 `output/final_report.md` 查看和修改**，告知用户可以：
   - 直接用编辑器打开文件自行修改，改完后回到对话输入 `/confirm`
   - 或直接在对话中提出修改意见，由 LLM 更新报告后再请用户确认
5. 用户可多次往返修改，直到满意后输入 `/confirm` 推进至 S6

**输出产物**：`output/final_report.md`（对话路径不生成 `.anappt/s5_report.md`）

**工具子集**：`read_file`/`write_artifact`/`read_memory`/`read_history`

**is_ready 校验**：`output/final_report.md` 存在、非空，且包含至少 2 个一级标题（`# ` 开头）

**审核要点**：
- 报告结构是否清晰
- 语言是否适合目标受众
- 结论是否有数据支撑
- 建议是否具体可执行

> **重要**：S5 完成后，系统会提示用户打开 `output/final_report.md` 查看和修改。用户可以：
> 1. 直接编辑 `output/final_report.md` 文件
> 2. 在终端中描述修改意见，由 LLM 更新报告后再次等待 `/confirm`
> 3. 确认后进入 S6（PPT 生成）

### 阶段间审核机制

每个阶段完成后，状态变为 `awaiting_review`，系统支持以下 6 个元命令（均以 `/` 开头，大小写不敏感）：

1. **`/confirm`**：接受当前输出，进入下一阶段
   - 调用阶段 `is_ready` 校验，若不通过则提示并保持在当前阶段
   - 通过后触发 Git 提交：`feat(S1): confirm 选题与目标定义`

2. **`/exit`**：保存当前进度并退出
   - 触发 Git 提交：`chore: auto-save on exit`
   - 下次可用 `anappt resume` 继续

3. **`/status`**：打印当前流水线状态表（阶段 ID、名称、状态、迭代次数）

4. **`/memory`**：打印项目记忆 `.anappt/memory.md`

5. **`/help`**：打印元命令帮助

6. **`/ppt <需求>`**：跳过 S1–S5 前置阶段，直达生成 PPT（详见 [PPT 生成流程](ppt-workflow.md)）

> **元命令必须以 `/` 开头**：裸单词（`confirm`/`exit`/`help`）与中文别名（`退出`/`帮助`）已移除。以 `/` 开头但非已知元命令的输入（如 `/foo`）也作为自由文本进入对话。
>
> **修改意见为自由文本**：当用户输入的内容不是元命令时，整段文本会作为对话消息进入当前阶段的 LLM 对话，由 LLM 根据反馈更新产出物后再次等待用户 `/confirm`。系统**不提供**独立的 `revise`/`config`/`reset` 系统操作。

### 产物文件一览

| 阶段 | 产物文件 | 说明 |
|------|---------|------|
| S1 | `report.yaml` | 项目根目录的报告规格书 |
| S1 | `.anappt/s1_topic.md` | 细化选题文档 |
| S2 | `.anappt/s2_data_requirement.md` | 数据需求文档 |
| S3 | `.anappt/s3_data_profile.md` | 数据档案 |
| S4 | `.anappt/s4_analysis_report.md` | 分析报告 |
| S5 | `output/final_report.md` | 最终分析报告 |
