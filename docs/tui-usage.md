# 交互式 TUI 使用指南 / Interactive TUI Usage Guide

---

## 中文

### 概述

AnaPPTAgent 的交互模式（TUI）提供了一个命令循环界面，用户可以在其中运行流水线、查看状态、确认/修改阶段输出、重置进度等。与直接使用 `anappt run` 不同，交互模式持续运行，直到用户主动退出。

### 启动交互模式

在项目目录中运行：

```bash
cd my_report
anappt interactive
```

> **注意**：必须在已创建的 AnaPPTAgent 项目目录中运行，否则会提示"未找到项目"。

### 界面显示

启动后会显示欢迎信息：
```
欢迎使用 AnaPPTAgent 交互模式
输入 'exit' 退出, 或输入命令:
>
```

### 可用命令

在交互模式的 `>` 提示符下，可以输入以下命令：

| 命令       | 说明                                     |
|------------|------------------------------------------|
| `confirm`  | 确认当前阶段输出，进入下一阶段           |
| `status`   | 显示所有阶段状态表格                     |
| `config`   | 显示当前模型配置                         |
| `reset`    | 重置所有阶段为 pending 状态              |
| `help`     | 显示可用命令列表                         |
| `exit`     | 退出交互模式（触发最终 Git 提交）        |
| 其他文本   | 尝试运行流水线或作为修改意见处理         |

### 命令详解

#### `confirm`

确认当前处于 `awaiting_review` 状态的阶段，将其标记为 `completed`，然后自动开始下一阶段。

```
> confirm
```

如果当前没有阶段等待确认，命令会被忽略。

#### `status`

以表格形式显示所有阶段的状态：

```
> status
ID | Name              | Status          | Iter
---+-------------------+-----------------+-----
S1 | 选题与目标定义     | completed       | 1
S2 | 数据需求分析       | completed       | 1
S3 | 数据加载与验证     | completed       | 1
S4 | 数据分析           | awaiting_review | 2
S5 | 报告生成           | pending         | 0
S6 | PPT 生成           | pending         | 0
```

#### `config`

显示当前的 LLM 模型配置：

```
> config
当前 LLM 配置
reasoning:
  provider: openai
  model: gpt-4o
  ...
```

#### `reset`

重置所有阶段为 `pending` 状态。**此操作不可逆**，会清除所有已完成的进度（但产物文件仍然保留）。

```
> reset
重置所有阶段...
```

#### `help`

显示可用命令列表：

```
> help
可用命令: status, config, reset, exit, confirm
```

#### `exit`

退出交互模式。退出时会自动执行一次 Git 提交（`chore: auto-save on exit`），保存所有未提交的更改。

```
> exit
退出中...
```

#### 其他输入（运行流水线 / 修改意见）

当输入不是上述任何命令时：
- 如果当前没有阶段在等待审核，会尝试启动流水线
- 如果当前有阶段处于 `awaiting_review` 状态，输入会被当作修改意见，重新运行该阶段

### 确认/修改循环

这是交互模式中最核心的工作流：

```
阶段 S1 执行完成
输入 confirm 确认, 或描述修改意见:
> 选题方向需要更聚焦在移动端
根据您的反馈进行修改...
阶段 S1 已完成。
输入 confirm 确认, 或描述修改意见:
> confirm
阶段 S1 已确认。
开始阶段 S2: 数据需求分析
...
```

**工作流程**：
1. 阶段执行完成后，状态变为 `awaiting_review`
2. 用户看到提示 `输入 confirm 确认, 或描述修改意见:`
3. 用户有两个选择：
   - 输入 `confirm` → 确认输出，进入下一阶段
   - 输入修改意见文本 → 阶段重新运行（迭代次数 +1），再次等待审核
4. 重复直到用户确认或退出

### Rich 与纯文本模式

交互 UI 会自动检测 `rich` 库是否可用：
- **Rich 模式**（默认）：使用彩色输出和格式化表格
- **纯文本模式**（rich 未安装时）：使用简单的文本输出和 ASCII 表格

两种模式功能完全相同，仅显示效果不同。

### 会话日志

每个阶段执行时，会自动记录会话日志到 `.anappt/session_history/YYYY-MM-DD.md`：

- **Agent 日志**：LLM 的输出内容
- **用户日志**：用户的修改意见

会话日志默认不被 Git 跟踪（`.gitignore` 中排除）。

### Git 自动提交

交互模式下，Git 自动提交在三个时机触发：

| 时机 | 提交信息格式 |
|------|-------------|
| 阶段内容生成完成 | `feat(S1): complete 选题与目标定义 - .anappt/s1_topic.md` |
| 用户确认阶段 | `feat(S1): confirm 选题与目标定义` |
| 退出交互模式 | `chore: auto-save on exit` |

> 如果项目目录不是 Git 仓库，所有提交操作会被静默跳过。

### 使用示例

#### 完整流程

```bash
# 1. 创建项目
anappt new my_report
cd my_report

# 2. 编辑配置
# (编辑 report.yaml)

# 3. 放入数据
cp ~/data.csv data/

# 4. 启动交互模式
anappt interactive

# 5. 在交互模式中：
>                    # 按回车开始流水线
# S1 执行完成...
> confirm            # 确认 S1
# S2 执行完成...
> 需要增加用户行为数据  # 修改 S2
# S2 重新执行...
> confirm            # 确认 S2
# S3 执行完成...
> confirm            # 确认 S3
# S4 执行完成...
> 分析不够深入，请增加趋势分析  # 修改 S4
# S4 重新执行...
> confirm            # 确认 S4
# S5 执行完成，报告已生成
> confirm            # 确认 S5
# S6 执行完成，PPT 已生成
> confirm            # 确认 S6，流水线完成
> exit               # 退出
```

#### 中途退出与恢复

```bash
# 第一次运行，做到 S4 后退出
anappt interactive
> (流水线运行到 S4 awaiting_review)
> exit

# 第二次继续
anappt interactive
> status             # 查看：S4 处于 awaiting_review
> confirm            # 继续 S5
```

---

## English

### Overview

AnaPPTAgent's interactive mode (TUI) provides a command-loop interface where users can run the pipeline, check status, confirm/revise stage outputs, reset progress, and more. Unlike running `anappt run` directly, interactive mode stays running until the user explicitly exits.

### Starting Interactive Mode

Run inside a project directory:

```bash
cd my_report
anappt interactive
```

> **Note**: Must be run inside an existing AnaPPTAgent project directory, otherwise it will report "No project found."

### Interface Display

Upon startup, a welcome message appears:
```
Welcome to AnaPPTAgent Interactive Mode
Enter 'exit' to quit, or enter a command:
>
```

### Available Commands

At the `>` prompt, the following commands are available:

| Command   | Description                                             |
|-----------|---------------------------------------------------------|
| `confirm` | Confirm current stage output and advance to next        |
| `status`  | Display all stage statuses as a table                   |
| `config`  | Show current model configuration                        |
| `reset`   | Reset all stages to pending status                      |
| `help`    | Show available commands                                 |
| `exit`    | Exit interactive mode (triggers final Git commit)       |
| Other     | Treated as pipeline run attempt or revision feedback    |

### Command Details

#### `confirm`

Confirms the stage currently in `awaiting_review` status, marks it as `completed`, and automatically starts the next stage.

```
> confirm
```

If no stage is awaiting review, the command is ignored.

#### `status`

Displays all stage statuses in a table:

```
> status
ID | Name                | Status          | Iter
---+---------------------+-----------------+-----
S1 | Topic Definition    | completed       | 1
S2 | Data Requirements   | completed       | 1
S3 | Data Loading        | completed       | 1
S4 | Data Analysis       | awaiting_review | 2
S5 | Report Generation   | pending         | 0
S6 | PPT Generation      | pending         | 0
```

#### `config`

Shows current LLM model configuration.

#### `reset`

Resets all stages to `pending` status. **This is irreversible** — all progress is cleared (but artifact files are preserved).

```
> reset
Resetting all stages...
```

#### `help`

Shows the list of available commands:

```
> help
Available commands: status, config, reset, exit, confirm
```

#### `exit`

Exits interactive mode. A final Git commit (`chore: auto-save on exit`) is automatically performed to save any uncommitted changes.

```
> exit
Exiting...
```

#### Other Input (Run Pipeline / Revision)

When input doesn't match any command:
- If no stage is awaiting review, it attempts to start the pipeline
- If a stage is in `awaiting_review`, the input is treated as revision feedback, re-running the stage

### Confirm/Revise Loop

This is the core workflow in interactive mode:

1. After a stage completes, its status becomes `awaiting_review`
2. User sees the prompt: `Enter confirm to proceed, or describe revision feedback:`
3. Two choices:
   - Type `confirm` → Accept output, advance to next stage
   - Type revision feedback text → Stage re-runs (iteration count +1), awaits review again
4. Repeat until confirmed or exited

### Rich vs Plain Text Mode

The interactive UI auto-detects the `rich` library:
- **Rich mode** (default): Colored output and formatted tables
- **Plain text mode** (rich not installed): Simple text output and ASCII tables

Both modes have identical functionality, differing only in display quality.

### Session Logging

Each stage execution automatically logs to `.anappt/session_history/YYYY-MM-DD.md`:
- **Agent logs**: LLM output content
- **User logs**: User revision feedback

Session logs are excluded from Git tracking by default (in `.gitignore`).

### Git Auto-Commit

In interactive mode, Git auto-commits trigger at three points:

| Trigger | Commit Message Format |
|---------|----------------------|
| Stage content generated | `feat(S1): complete Topic Definition - .anappt/s1_topic.md` |
| User confirms stage | `feat(S1): confirm Topic Definition` |
| Exit interactive mode | `chore: auto-save on exit` |

> If the project directory is not a Git repository, all commit operations are silently skipped.

### Usage Example

#### Complete Flow

```bash
# 1. Create project
anappt new my_report
cd my_report

# 2. Edit configuration
# (Edit report.yaml)

# 3. Place data
cp ~/data.csv data/

# 4. Start interactive mode
anappt interactive

# 5. In interactive mode:
>                    # Press Enter to start pipeline
# S1 completes...
> confirm            # Confirm S1
# S2 completes...
> Need more user behavior data  # Revise S2
# S2 re-runs...
> confirm            # Confirm S2
# S3 completes...
> confirm            # Confirm S3
# S4 completes...
> Analysis not deep enough, add trend analysis  # Revise S4
# S4 re-runs...
> confirm            # Confirm S4
# S5 completes, report generated
> confirm            # Confirm S5
# S6 completes, PPT generated
> confirm            # Confirm S6, pipeline complete
> exit               # Exit
```

#### Mid-Session Exit and Resume

```bash
# First run, exit after S4
anappt interactive
> (pipeline runs to S4 awaiting_review)
> exit

# Second run, continue
anappt interactive
> status             # Check: S4 is awaiting_review
> confirm            # Continue to S5
```
