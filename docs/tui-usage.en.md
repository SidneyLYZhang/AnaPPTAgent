# Interactive TUI Usage Guide

## Overview

AnaPPTAgent's interactive mode (TUI) provides a command-loop interface where users can run the pipeline, check status, confirm/revise stage outputs, reset progress, and more. Unlike running `anappt run` directly, interactive mode stays running until the user explicitly exits.

## Starting Interactive Mode

Run inside a project directory:

```bash
cd my_report
anappt interactive
```

> **Note**: Must be run inside an existing AnaPPTAgent project directory, otherwise it will report "No project found."

## Interface Display

Upon startup, a welcome message appears:

```
Welcome to AnaPPTAgent Interactive Mode
Type 'exit' to quit, or enter a command:
>
```

## Available Commands

At the `>` prompt, the following commands are available:

| Command   | Description                                             |
|-----------|---------------------------------------------------------|
| `confirm` | Confirm current stage output and advance to next        |
| `status`  | Display all stage statuses as a table                   |
| `config`  | Show current model configuration                        |
| `reset`   | Reset all stages to pending status                      |
| `help`    | Show available commands                                 |
| `exit`    | Exit interactive mode (triggers final Git commit)      |
| Other     | Treated as pipeline run attempt or revision feedback   |

## Command Details

### `confirm`

Confirms the stage currently in `awaiting_review` status, marks it as `completed`, and automatically starts the next stage.

```
> confirm
```

If no stage is awaiting review, the command is ignored.

### `status`

Displays all stage statuses in a table:

```
> status
ID | Name                | Status          | Iter
---+---------------------+-----------------+-----
S1 | Topic & Goal Definition | completed       | 1
S2 | Data Requirement Analysis | completed       | 1
S3 | Data Loading & Validation | completed       | 1
S4 | Data Analysis       | awaiting_review | 2
S5 | Report Generation   | pending         | 0
S6 | PPT Generation      | pending         | 0
```

### `config`

Shows current LLM model configuration:

```
> config
Current LLM configuration
reasoning:
  provider: openai
  model: gpt-4o
  ...
```

### `reset`

Resets all stages to `pending` status. **This is irreversible** — all progress is cleared (but artifact files are preserved).

```
> reset
Resetting all stages...
```

### `help`

Shows the list of available commands:

```
> help
Available commands: status, config, reset, exit, confirm
```

### `exit`

Exits interactive mode. A final Git commit (`chore: auto-save on exit`) is automatically performed to save any uncommitted changes.

```
> exit
Exiting...
```

### Other Input (Run Pipeline / Revision)

When input doesn't match any command:
- If no stage is awaiting review, it attempts to start the pipeline
- If a stage is in `awaiting_review`, the input is treated as revision feedback, re-running the stage

## Confirm/Revise Loop

This is the core workflow in interactive mode:

```
Stage S1 completed
Enter 'confirm' to proceed, or describe your revision:
> The topic should focus more on mobile
Revising based on your feedback...
Stage S1 completed.
Enter 'confirm' to proceed, or describe your revision:
> confirm
Stage S1 confirmed.
Starting stage S2: Data Requirement Analysis
...
```

**Workflow**:
1. After a stage completes, its status becomes `awaiting_review`
2. User sees the prompt `Enter 'confirm' to proceed, or describe your revision:`
3. Two choices:
   - Type `confirm` → Accept output, advance to next stage
   - Type revision feedback text → Stage re-runs (iteration count +1), awaits review again
4. Repeat until confirmed or exited

## Rich vs Plain Text Mode

The interactive UI auto-detects the `rich` library:
- **Rich mode** (default): Colored output and formatted tables
- **Plain text mode** (rich not installed): Simple text output and ASCII tables

Both modes have identical functionality, differing only in display quality.

## Session Logging

Each stage execution automatically logs to `.anappt/session_history/{stage_id}_session.md` (e.g., `S1_session.md`):

- **Agent logs**: LLM output content
- **User logs**: User revision feedback

Session logs are excluded from Git tracking by default (in `.gitignore`).

## Git Auto-Commit

In interactive mode, Git auto-commits trigger at three points:

| Trigger | Commit Message Format |
|---------|----------------------|
| Stage content generated | `feat(S1): complete Topic & Goal Definition - .anappt/s1_topic.md` |
| User confirms stage | `feat(S1): confirm Topic & Goal Definition` |
| Exit interactive mode | `chore: auto-save on exit` |

> If the project directory is not a Git repository, all commit operations are silently skipped.

## Usage Example

### Complete Flow

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

### Mid-Session Exit and Resume

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
