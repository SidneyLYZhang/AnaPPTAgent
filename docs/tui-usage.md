# 对话式 TUI 使用指南

## 概述

AnaPPTAgent 的 TUI 是一个**统一的对话式界面**（`ConversationRunner`）：LLM 在每个阶段通过多轮对话驱动产出，用户与 LLM 在同一对话循环中协作。LLM 分析当前阶段进展、按需调用授权工具完成实际操作（读写产出物、执行 Python、Web 搜索/读取、渲染/导出 PPT、读取历史、更新记忆），并引导用户在产出就绪后通过 `confirm` 元命令确认推进。

`anappt run` 与 `anappt interactive` 均进入同一个 `ConversationRunner`，差异仅在于启动时注入系统提示的上下文范围（详见[启动方式](#启动方式)）。对话持续运行，直到用户输入 `exit` 主动退出。

!!! info "门控规则"
    阶段推进严格由人控制：只有 `confirm` 元命令（且当前阶段 `is_ready` 校验通过后）才能将阶段标记为 `completed` 并推进到下一阶段。**LLM 不可自行推进阶段**，在用户 `confirm` 前不得宣告阶段已完成。

## 启动方式

在已创建的 AnaPPTAgent 项目目录中运行以下任一命令：

```bash
cd my_report
anappt run          # 或 anappt resume（两者等价）
anappt interactive
```

> **注意**：必须在已初始化的项目目录（含 `.anappt/state.yaml`）中运行，否则会提示"未找到项目"。

两种启动方式的差异：

| 启动命令 | 系统提示上下文 | 行为 |
|----------|---------------|------|
| `anappt run` / `anappt resume` | 阶段进展 + 项目记忆 + 当前阶段工具 | 聚焦当前阶段，恢复门控流水线对话；若产出未就绪则说明还缺什么，已就绪则提示用户 `confirm` 推进 |
| `anappt interactive` | 阶段进展 + 项目记忆 + **全部阶段状态** + **近期会话历史索引** + **当前产出物清单** | LLM 自识别用户当前需要做的事情并主动提示；可跨阶段提供建议，但仍不可自行推进 |

两者进入同一 `ConversationRunner`，元命令、工具体系、会话日志、Git 提交逻辑完全一致。

## 界面显示

启动后不再展示固定的"按回车开始流水线"流程。**阶段入口由 LLM 先生成开场提示**：

- `anappt run` 模式注入 `conv.opening_instruction`：LLM 基于当前阶段进展与项目记忆，分析进度并指出下一步。
- `anappt interactive` 模式注入 `conv.opening_instruction_interactive`：LLM 基于全部阶段进展、项目记忆、近期会话历史索引与当前产出物，自识别用户当前需要做的事情并生成开场提示。

开场提示打印后，进入 `>` 提示符等待用户输入：

```
（LLM 开场提示：分析当前进度，指出下一步）
>
```

## 可用元命令

在 `>` 提示符下，可以输入以下 5 个元命令（大小写不敏感）：

| 元命令 | 说明 |
|--------|------|
| `confirm` | 校验当前阶段 `is_ready` 通过后推进到下一阶段；未就绪则拒绝 |
| `exit` | 生成会话核心摘要 → 判断是否更新项目记忆 → Git 提交 → 退出 |
| `status` | 打印所有阶段的状态表 |
| `memory` | 打印项目记忆（`.anappt/memory.md` 内容） |
| `help` | 列出可用元命令 |

!!! tip "别名"
    `exit` 也接受 `quit` / `退出`；`help` 也接受 `帮助`。除上述 5 个元命令外，其它输入均作为自由文本进入 LLM 对话（见[自由文本对话](#自由文本对话)）。

## 元命令详解

### `confirm`

校验当前阶段的 `is_ready` 门控：若产出就绪，将阶段状态推进至 `completed`，保存状态，触发 Git 提交，然后进入下一阶段（或若流水线已完成则退出）；若未就绪，打印拒绝信息并返回，LLM 不可自行推进。

```
> confirm
阶段 S1 已确认并推进。
（LLM 生成 S2 阶段开场提示）
>
```

### `status`

以表格形式打印所有阶段的状态：

```
> status
当前流水线状态:
ID | Name              | Status          | Iter
---+-------------------+-----------------+-----
S1 | 选题与目标定义     | completed       | 1
S2 | 数据需求分析       | completed       | 1
S3 | 数据加载与验证     | completed       | 1
S4 | 数据分析           | awaiting_review | 2
S5 | 报告生成           | pending         | 0
S6 | PPT 生成           | pending         | 0
```

### `memory`

打印项目记忆文件 `.anappt/memory.md` 的完整内容。若记忆为空，打印占位提示。详见[项目记忆](#项目记忆)。

```
> memory
（.anappt/memory.md 的完整内容）
```

### `help`

列出可用元命令：

```
> help
可用元命令: confirm(确认推进) / status(查看状态) / memory(查看记忆) / help(帮助) / exit(退出)。其它输入作为对话内容进入 LLM。
```

### `exit`

退出对话循环，依次执行（每步均为 best-effort）：

1. 调用 LLM 为当前会话生成核心摘要
2. 将会话日志刷写到磁盘
3. 调用 LLM 判断是否需要更新项目记忆（有进展则更新、无进展则不更新）
4. 触发 `commit_on_exit` Git 提交

```
> exit
（生成会话摘要、更新记忆、Git 提交）
```

## 自由文本对话

在 `>` 提示符下输入的任何非元命令文本，都会作为用户消息进入 LLM 对话（携带跨轮持久化的对话历史）。LLM 会结合上下文回复，并可调用当前阶段授权的工具子集执行实际操作（如读写产出物、执行分析代码、搜索资料等）。

```
> 选题方向需要更聚焦在移动端用户增长
（LLM 调用 write_artifact 更新 report.yaml / s1_topic.md，并回复）
> 数据需求里需要补充用户留存指标
（LLM 更新 s2_data_requirement.md 并回复）
```

对话历史在同一阶段内跨轮持久化；当用户 `confirm` 推进到下一阶段时，历史清空并重新开始。

## LLM 工具体系

LLM 在对话中可调用以下 10 个工具执行实际操作。每个阶段仅启用其授权子集，未授权的工具调用会被系统拒绝。

| 工具 | 说明 |
|------|------|
| `read_file` | 读取项目目录下的文件内容（UTF-8） |
| `write_artifact` | 写入阶段产出物（父目录自动创建） |
| `read_memory` | 读取项目记忆（`.anappt/memory.md`） |
| `read_history` | 按阶段 ID / 日期 / 全部读取历史会话文档 |
| `list_stage_artifacts` | 列出指定阶段声明的产出物及是否存在 |
| `execute_python` | 在沙箱中执行 Python 代码（网络隔离，文件访问限定 `data/` 与 `output/`） |
| `search_web` | Web 搜索（返回标题、URL、摘要） |
| `fetch_url` | 读取网页内容转 Markdown（需 `JINA_API_KEY`） |
| `render_deck` | 渲染 PPT HTML（基于 dashi-ppt-skill） |
| `export_pptx` | 导出 PPTX（或 PDF） |

各阶段启用的工具子集：

| 阶段 | 启用工具 |
|------|---------|
| S1 选题与目标定义 | `read_file` / `write_artifact` / `read_memory` / `read_history` |
| S2 数据需求分析 | `read_file` / `write_artifact` / `read_memory` / `read_history` |
| S3 数据加载与验证 | `read_file` / `write_artifact` / `execute_python` / `read_memory` / `read_history` |
| S4 数据分析 | `read_file` / `write_artifact` / `execute_python` / `search_web` / `fetch_url` / `read_memory` / `read_history` |
| S5 报告生成 | `read_file` / `write_artifact` / `read_memory` / `read_history` |
| S6 PPT 生成 | `read_file` / `write_artifact` / `render_deck` / `export_pptx` / `read_memory` / `read_history` |

## 阶段产出物

各阶段的权威产出物路径如下（`write_artifact` 工具按此路径写入）：

| 阶段 | 产出物路径 |
|------|-----------|
| S1 | `report.yaml`（项目根）+ `.anappt/s1_topic.md` |
| S2 | `.anappt/s2_data_requirement.md` |
| S3 | `.anappt/s3_data_profile.md` |
| S4 | `.anappt/s4_analysis_report.md` |
| S5 | `output/final_report.md` |
| S6 | `output/ppt/goal.json` + `output/ppt/presentation.html`（+ 可选 `output/ppt/presentation.pptx`） |

`confirm` 推进时，系统通过 `is_ready` 校验当前阶段产出物是否就绪（通常检查文件是否存在且非空）。

## 会话日志

每个阶段的对话自动记录到 `.anappt/session_history/` 目录，文件名格式为 `YYYY-MM-DD_<stage>.md`（UTC 日期），如 `2024-12-01_S1.md`。

每个日志文件的结构：

```markdown
## 核心摘要
（LLM 在会话退出时生成的 1-3 句中文摘要）

### 对话记录

## Agent

[2024-12-01T10:30:00Z]

（LLM 的回复内容）

## 用户

[2024-12-01T10:30:15Z]

（用户的输入内容）
```

- **同日同阶段**的多次会话以 `---` 分隔追加到同一文件，而非覆盖。
- **核心摘要**由 LLM 在 `exit` 时为当前缓冲会话生成，置于该次会话块顶部。
- 会话日志默认被 `.gitignore` 排除，不纳入 Git 跟踪。

## 项目记忆

项目记忆保存在 `.anappt/memory.md`，由 `MemoryManager` 维护，是跨会话持久化的项目进展、关键决策与重要上下文记录。

- **读取**：LLM 可通过 `read_memory` 工具随时读取；系统提示中也会自动注入当前记忆内容。
- **更新**：仅在会话退出（`exit`）时，由 LLM 判断本次会话是否有需要记入的进展：
    - 有进展 → LLM 输出更新后的完整 `memory.md` 内容（保留已有时间戳，追加带日期 `YYYY-MM-DD` 的新条目）。
    - 无进展 → LLM 输出 `NO_UPDATE`，文件保持不变。
- 用户可通过 `memory` 元命令查看当前记忆内容。

## 历史按需读取

LLM 可通过 `read_history` 工具按需读取 `.anappt/session_history/` 下的历史会话文档，参数 `target` 支持：

| `target` 值 | 匹配范围 |
|-------------|---------|
| `all`（默认） | 目录下所有 `*.md` 文件 |
| `YYYY-MM-DD`（日期） | 文件名以该日期开头的文件 |
| 阶段 ID（如 `S4`） | 文件名阶段段等于该 ID 的文件（如 `2024-12-01_S4.md`） |

匹配的文件内容按文件名排序后以 `---` 分隔拼接返回。这使得 LLM 可以回溯过往会话的对话记录与核心摘要，为当前阶段提供上下文。

在 `anappt interactive` 模式下，系统提示还会注入近期会话历史的文件名索引（最多 20 个，按名称倒序），帮助 LLM 感知有哪些历史可读。

## Git 自动提交

对话模式下，Git 自动提交在三个时机触发：

| 时机 | 提交信息格式 |
|------|-------------|
| 阶段产出完成 | `feat(S1): complete 选题与目标定义 - <files>` |
| 用户 `confirm` 推进 | `feat(S1): confirm 选题与目标定义` |
| 退出（`exit`） | `chore: auto-save on exit` |

提交信息通过 `t()` 本地化。若项目目录不是 Git 仓库，所有提交操作会被静默跳过。会话历史目录（`.anappt/session_history/`）会被排除在提交之外。

## Rich 与纯文本模式

交互 UI 会自动检测 `rich` 库是否可用：

- **Rich 模式**（默认）：使用彩色输出和格式化表格
- **纯文本模式**（rich 未安装时）：使用简单的文本输出和 ASCII 表格

两种模式功能完全相同，仅显示效果不同。

## 使用示例

### 完整对话流程

```bash
# 1. 创建项目
anappt new my_report
cd my_report

# 2. 放入数据
cp ~/data.csv data/

# 3. 启动对话式 TUI
anappt interactive

# 4. 对话过程：
# （LLM 开场：检测到 report.yaml 尚未填写，提示先确认选题方向）
> 我想分析移动端用户增长趋势，受众是产品团队
# （LLM 调用 write_artifact 写入 report.yaml 与 .anappt/s1_topic.md，回复确认）
> confirm
# 阶段 S1 已确认并推进。
# （LLM 生成 S2 开场：基于 S1 选题分析数据需求）
> 需要补充用户留存与活跃度指标
# （LLM 更新 s2_data_requirement.md）
> confirm
# 阶段 S2 已确认并推进。
# （LLM 生成 S3 开场：调用 execute_python 扫描 data/ 并生成数据 profile）
> confirm
# 阶段 S3 已确认并推进。
# （LLM 生成 S4 开场：调用 execute_python 分析数据）
> 请增加月度趋势分析
# （LLM 调用 execute_python 执行分析，更新 s4_analysis_report.md）
> confirm
# 阶段 S4 已确认并推进。
# （LLM 生成 S5 开场：撰写分析报告）
> confirm
# 阶段 S5 已确认并推进，报告已生成到 output/final_report.md
# （LLM 生成 S6 开场：构造 goal.json 并渲染 PPT）
> confirm
# 阶段 S6 已确认并推进。全部阶段已完成,项目交付。
> exit
# （生成会话摘要、更新记忆、Git 提交，退出）
```

### 中途退出与恢复

```bash
# 第一次运行，做到 S4 后退出
anappt run
# （LLM 开场：当前处于 S4，产出尚未就绪）
> exit
# （会话摘要写入、Git 提交）

# 第二次继续——run 与 interactive 均可恢复
anappt run
# （LLM 开场：读取状态，发现 S4 进行中，提示继续分析）
> status
# S4 | 数据分析 | in_progress | 1
# （继续 S4 对话）
> confirm
# 阶段 S4 已确认并推进。
```
