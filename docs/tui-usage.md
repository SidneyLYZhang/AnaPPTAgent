# 对话式 TUI 使用指南

## 概述

AnaPPTAgent 的 TUI 是一个基于 [textual](https://textual.textualize.io/) 的**全屏对话式界面**（`ConversationRunner` + `ReportBuilderApp`）：LLM 在每个阶段通过多轮对话驱动产出，用户与 LLM 在同一对话循环中协作。LLM 分析当前阶段进展、按需调用授权工具完成实际操作（读写产出物、执行 Python、Web 搜索/读取、渲染/导出 PPT、读取历史、更新记忆），并引导用户在产出就绪后通过 `/confirm` 元命令确认推进。

TUI 提供结构化的对话布局、流式 LLM 输出与实时「思考滚动条」、以及 `/` 前缀元命令（在任何语言环境下都不歧义）。`anappt run`、`anappt resume` 与 `anappt interactive` 均进入同一个 textual TUI，差异仅在于启动时注入系统提示的上下文范围（详见[启动方式](#启动方式)）。对话持续运行，直到用户输入 `/exit` 主动退出。

!!! info "门控规则"
    阶段推进严格由人控制：只有 `/confirm` 元命令（且当前阶段 `is_ready` 校验通过后）才能将阶段标记为 `completed` 并推进到下一阶段。**LLM 不可自行推进阶段**，在用户 `/confirm` 前不得宣告阶段已完成。

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
| `anappt run` / `anappt resume` | 阶段进展 + 项目记忆 + 当前阶段工具 | 聚焦当前阶段，恢复门控流水线对话；若产出未就绪则说明还缺什么，已就绪则提示用户 `/confirm` 推进 |
| `anappt interactive` | 阶段进展 + 项目记忆 + **全部阶段状态** + **近期会话历史索引** + **当前产出物清单** | LLM 自识别用户当前需要做的事情并主动提示；可跨阶段提供建议，但仍不可自行推进 |

三者进入同一 textual TUI，元命令、工具体系、会话日志、Git 提交逻辑完全一致。

## 界面显示

启动后进入 textual 全屏 TUI，布局自上而下分为五部分：

```
┌──────────────────────────────────────────────────────────────────┐
│ 📋 报告构建助手 · 步骤 X/6：<阶段名>                   (标题栏)  │
├──────────────────────────────────────────────────────────────────┤
│ 🤖 助手：……                                                       │
│ 👤 你：……                                                         │
│ 系统：……                                                          │
│                                                                   │
│   （对话历史区 #chat，柔性高度，PgUp/PgDn 翻页）                   │
├──────────────────────────────────────────────────────────────────┤
│ ✦ 思考中 ⣾ …<流式尾部>▍                              (思考滚动条)│
├──────────────────────────────────────────────────────────────────┤
│ 请输入（/help 查看命令，Enter 发送…）                  (输入区)  │
├──────────────────────────────────────────────────────────────────┤
│ Enter 发送 · Shift+Enter 换行 · PgUp/PgDn 翻历史 · /exit 退出     │
└──────────────────────────────────────────────────────────────────┘
```

1. **标题栏**（Header）：显示 `📋 报告构建助手 · 步骤 X/6：<阶段名>`；全部阶段完成后显示「已完成全部阶段」。
2. **对话历史区**（`#chat` RichLog）：柔性高度，以 `🤖 助手：` / `👤 你：` 区分角色；系统输出（`/status`、`/memory`、`/help` 等）也写入此区。支持 PgUp/PgDn 翻页，用户上翻时暂停吸底。
3. **思考滚动条**（`#thinking` 单行 Static）：仅 LLM 流式输出期间显示（详见[流式 LLM](#流式-llm)）。
4. **输入区**（`#input` 多行 TextArea，高亮边框）：Enter 发送、Shift+Enter 换行。
5. **快捷键提示栏**（Footer）：`Enter 发送 · Shift+Enter 换行 · PgUp/PgDn 翻历史 · /exit 退出`。

### 流式 LLM

LLM 回复采用流式读取，分三种状态：

- **等待首个 token**：思考滚动条显示 `✦ 思考中 ⣾ 正在组织思路…`，避免空白行让用户以为卡死。
- **流式输出中**：思考滚动条显示 `✦ 思考中 ⣾ …<流式尾部>▍`，每 100ms 刷新一帧 spinner（braille 动画），尾部按显示宽度截取（CJK 字符占 2 列）。reasoning 增量优先展示，否则展示 content 增量。
- **输出完成**：思考滚动条隐藏，整段回复以 `🤖 助手：` 写入对话历史区。

工具调用迭代期间同样走流式：每轮工具调用前显示「正在组织思路…」占位，流结束后执行工具并继续下一轮流式，直到 LLM 不再返回工具调用。阶段入口的开场提示也以流式方式生成：`anappt run` 模式注入 `conv.opening_instruction`，`anappt interactive` 模式注入 `conv.opening_instruction_interactive`。

## 可用元命令

在输入区中以 `/` 开头输入元命令（大小写不敏感）。系统识别以下 6 个元命令：

| 元命令 | 说明 |
|--------|------|
| `/confirm` | 校验当前阶段 `is_ready` 通过后推进到下一阶段；未就绪则拒绝 |
| `/exit` | 生成会话核心摘要 → 判断是否更新项目记忆 → Git 提交 → 退出 |
| `/status` | 打印所有阶段的状态表 |
| `/memory` | 打印项目记忆（`.anappt/memory.md` 内容） |
| `/help` | 列出可用元命令 |
| `/ppt <需求>` | 跳过 S1–S5 前置准备，直接调用 dashi-ppt-skill 生成 PPT（详见 [`/ppt` 直达生成](#ppt-直达生成)） |

!!! info "为何要求 `/` 前缀"
    元命令必须以 `/` 开头，这样在任何语言环境下都能与自由文本无歧义区分（英语环境下裸单词 `confirm`/`exit` 易与对话内容混淆）。**已移除**旧版的裸单词（`confirm`/`exit`/`help`/`quit`）与中文别名（`退出`/`帮助`）。

    - 以 `/` 开头但第一个 token 非已知元命令的输入（如 `/foo bar`）**作为自由文本**进入 LLM 对话。
    - 不以 `/` 开头的输入也作为自由文本进入 LLM 对话。

## 元命令详解

### `/confirm`

校验当前阶段的 `is_ready` 门控：若产出就绪，将阶段状态推进至 `completed`，保存状态，触发 Git 提交，然后进入下一阶段（或若流水线已完成则退出）；若未就绪，打印拒绝信息并返回，LLM 不可自行推进。

```
> /confirm
阶段 S1 已确认并推进。
（LLM 流式生成 S2 阶段开场提示）
>
```

### `/status`

以表格形式打印所有阶段的状态（写入对话历史区）：

```
> /status
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

### `/memory`

打印项目记忆文件 `.anappt/memory.md` 的完整内容。若记忆为空，打印占位提示。详见[项目记忆](#项目记忆)。

```
> /memory
（.anappt/memory.md 的完整内容）
```

### `/help`

列出可用元命令：

```
> /help
可用元命令（/ 前缀）: /confirm(确认推进) /status(查看状态) /memory(查看记忆) /help(帮助) /exit(退出) /ppt <需求>(直达生成 PPT)。其它输入作为对话内容进入 LLM。
```

### `/exit`

退出对话循环，依次执行（每步均为 best-effort）：

1. 调用 LLM 为当前会话生成核心摘要
2. 将会话日志刷写到磁盘
3. 调用 LLM 判断是否需要更新项目记忆（有进展则更新、无进展则不更新）
4. 触发 `commit_on_exit` Git 提交

```
> /exit
（生成会话摘要、更新记忆、Git 提交）
```

## `/ppt` 直达生成

`/ppt <需求>` 是一条独立的 PPT 直达生成命令：跳过 S1–S5 前置准备，直接调用 dashi-ppt-skill 能力生成 PPT。

- **用法**：`/ppt 生成关于 Q3 移动端用户增长的 10 页 PPT`（`/ppt` 后空格分隔写明 PPT 生成需求；空需求会提示用法并返回）。
- **行为**：加载 dashi-ppt `SKILL.md` 作为 LLM 系统提示，临时启用 S6 阶段的工具子集（见[各阶段启用工具](#llm-工具体系) S6 行，含 `read_file` / `write_artifact` / `render_deck` / `export_pptx` 等），以用户需求为 user 消息跑一轮流式 LLM turn（含工具调用迭代），驱动 LLM 构造 `output/ppt/goal.json` 并调用 `render_deck` 渲染 `output/ppt/presentation.html`。**不需要** `final_report.md`。
- **不影响门控流水线**：该命令不改变 `state.yaml` 的阶段状态，也不写入主对话历史 `self.messages`，是一段独立的直达生成；但该轮用户需求与 LLM 回复会记入当前会话日志。
- **skill 未安装**：提示运行 `anappt setup` 安装，不发起 LLM 调用。
- **完成后**：提示用户在浏览器中浏览确认；如需调整可继续对话，满意后可 `/exit` 退出。

```
> /ppt 生成关于 Q3 移动端用户增长的 10 页 PPT
（思考滚动条流式展示 LLM 构造 goal.json、调用 render_deck 的过程）
PPT 已生成，请在浏览器中浏览确认。如需调整可继续对话，满意后可输入 /exit 退出。
```

## 自由文本对话

在输入区中不以 `/` 开头的任何文本，都会作为用户消息进入 LLM 对话（携带跨轮持久化的对话历史），并以 `👤 你：` 写入对话历史区。LLM 会结合上下文回复（流式输出，完成后以 `🤖 助手：` 写入），并可调用当前阶段授权的工具子集执行实际操作（如读写产出物、执行分析代码、搜索资料等）。

```
> 选题方向需要更聚焦在移动端用户增长
（LLM 流式输出，调用 write_artifact 更新 report.yaml / s1_topic.md，完成后写入对话区）
> 数据需求里需要补充用户留存指标
（LLM 更新 s2_data_requirement.md 并回复）
```

对话历史在同一阶段内跨轮持久化；当用户 `/confirm` 推进到下一阶段时，历史清空并重新开始。

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

`/confirm` 推进时，系统通过 `is_ready` 校验当前阶段产出物是否就绪（通常检查文件是否存在且非空）。

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
- **核心摘要**由 LLM 在 `/exit` 时为当前缓冲会话生成，置于该次会话块顶部。
- 会话日志默认被 `.gitignore` 排除，不纳入 Git 跟踪。

## 项目记忆

项目记忆保存在 `.anappt/memory.md`，由 `MemoryManager` 维护，是跨会话持久化的项目进展、关键决策与重要上下文记录。

- **读取**：LLM 可通过 `read_memory` 工具随时读取；系统提示中也会自动注入当前记忆内容。
- **更新**：仅在会话退出（`/exit`）时，由 LLM 判断本次会话是否有需要记入的进展：
    - 有进展 → LLM 输出更新后的完整 `memory.md` 内容（保留已有时间戳，追加带日期 `YYYY-MM-DD` 的新条目）。
    - 无进展 → LLM 输出 `NO_UPDATE`，文件保持不变。
- 用户可通过 `/memory` 元命令查看当前记忆内容。

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
| 用户 `/confirm` 推进 | `feat(S1): confirm 选题与目标定义` |
| 退出（`/exit`） | `chore: auto-save on exit` |

提交信息通过 `t()` 本地化。若项目目录不是 Git 仓库，所有提交操作会被静默跳过。会话历史目录（`.anappt/session_history/`）会被排除在提交之外。

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
# （LLM 流式开场：检测到 report.yaml 尚未填写，提示先确认选题方向）
> 我想分析移动端用户增长趋势，受众是产品团队
# （LLM 流式输出，调用 write_artifact 写入 report.yaml 与 .anappt/s1_topic.md，回复确认）
> /confirm
# 阶段 S1 已确认并推进。
# （LLM 流式生成 S2 开场：基于 S1 选题分析数据需求）
> 需要补充用户留存与活跃度指标
# （LLM 更新 s2_data_requirement.md）
> /confirm
# 阶段 S2 已确认并推进。
# （LLM 流式生成 S3 开场：调用 execute_python 扫描 data/ 并生成数据 profile）
> /confirm
# 阶段 S3 已确认并推进。
# （LLM 流式生成 S4 开场：调用 execute_python 分析数据）
> 请增加月度趋势分析
# （LLM 调用 execute_python 执行分析，更新 s4_analysis_report.md）
> /confirm
# 阶段 S4 已确认并推进。
# （LLM 流式生成 S5 开场：撰写分析报告）
> /confirm
# 阶段 S5 已确认并推进，报告已生成到 output/final_report.md
# （LLM 流式生成 S6 开场：构造 goal.json 并渲染 PPT）
> /confirm
# 阶段 S6 已确认并推进。全部阶段已完成,项目交付。
> /exit
# （生成会话摘要、更新记忆、Git 提交，退出）
```

### `/ppt` 直达生成

```bash
anappt run
# （LLM 流式开场）
> /ppt 生成关于 Q3 移动端用户增长的 10 页 PPT
# （思考滚动条流式展示 LLM 构造 goal.json、调用 render_deck 的过程）
# PPT 已生成，请在浏览器中浏览确认。如需调整可继续对话，满意后可输入 /exit 退出。
> /exit
```

### 中途退出与恢复

```bash
# 第一次运行，做到 S4 后退出
anappt run
# （LLM 流式开场：当前处于 S4，产出尚未就绪）
> /exit
# （会话摘要写入、Git 提交）

# 第二次继续——run 与 interactive 均可恢复
anappt run
# （LLM 流式开场：读取状态，发现 S4 进行中，提示继续分析）
> /status
# S4 | 数据分析 | in_progress | 1
# （继续 S4 对话）
> /confirm
# 阶段 S4 已确认并推进。
```
