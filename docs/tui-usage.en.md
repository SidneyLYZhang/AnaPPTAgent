# Conversational TUI Usage Guide

## Overview

AnaPPTAgent's TUI is a **full-screen conversational interface** built on [textual](https://textual.textualize.io/) (`ConversationRunner` + `ReportBuilderApp`): the LLM drives stage outputs through multi-turn conversation, and the user collaborates with the LLM in the same dialog loop. The LLM analyzes the current stage progress, calls authorized tools on demand to perform real operations (read/write artifacts, execute Python, web search/fetch, render/export PPT, read history, update memory), and guides the user to confirm advancement via the `/confirm` meta-command once outputs are ready.

The TUI provides a structured conversation layout, streaming LLM output with a live "thinking bar", and `/`-prefixed meta-commands (unambiguous in any locale). `anappt run`, `anappt resume`, and `anappt interactive` all enter the same textual TUI. The only difference is the context scope injected into the system prompt at startup (see [Startup Modes](#startup-modes)). The conversation runs until the user types `/exit`.

!!! info "Gating Rules"
    Stage advancement is strictly human-controlled: only the `/confirm` meta-command (after the current stage's `is_ready` check passes) can mark a stage as `completed` and advance to the next. **The LLM cannot self-advance stages** and must not declare a stage complete before the user types `/confirm`.

## Startup Modes

Run either command inside an existing AnaPPTAgent project directory:

```bash
cd my_report
anappt run          # or anappt resume (equivalent)
anappt interactive
```

> **Note**: Must be run inside an initialized project directory (containing `.anappt/state.yaml`), otherwise it reports "No project found."

Differences between the two startup modes:

| Command | System-prompt context | Behavior |
|---------|----------------------|----------|
| `anappt run` / `anappt resume` | Stage progress + project memory + current-stage tools | Focuses on the current stage to resume the gated pipeline conversation; if outputs are not ready, explains what is missing; if ready, prompts the user to `/confirm` |
| `anappt interactive` | Stage progress + project memory + **all stage states** + **recent session-history index** + **current artifacts listing** | The LLM self-identifies what the user needs to do now and proactively prompts; may offer cross-stage suggestions, but still cannot self-advance |

All three enter the same textual TUI with identical meta-commands, tool system, session logging, and Git commit logic.

## Interface Display

Upon startup, a full-screen textual TUI appears. The layout, top to bottom, has five parts:

```
┌──────────────────────────────────────────────────────────────────┐
│ 📋 Report Builder · Step X/6: <stage name>             (Header)  │
├──────────────────────────────────────────────────────────────────┤
│ 🤖 Assistant: ……                                                  │
│ 👤 You: ……                                                        │
│ System: ……                                                        │
│                                                                   │
│   (Chat history #chat, flexible height, PgUp/PgDn to scroll)      │
├──────────────────────────────────────────────────────────────────┤
│ ✦ Thinking ⣾ …<stream tail>▍                              (Bar)  │
├──────────────────────────────────────────────────────────────────┤
│ Type here (/help for commands, Enter to send…)         (Input)   │
├──────────────────────────────────────────────────────────────────┤
│ Enter send · Shift+Enter newline · PgUp/PgDn scroll · /exit quit  │
└──────────────────────────────────────────────────────────────────┘
```

1. **Header**: shows `📋 Report Builder · Step X/6: <stage name>`; once all stages are complete it shows "All stages complete".
2. **Chat history** (`#chat` RichLog): flexible height; `🤖 Assistant:` / `👤 You:` distinguish roles. System output (`/status`, `/memory`, `/help`, etc.) is also written here. Supports PgUp/PgDn paging; auto-scroll-to-bottom pauses while the user scrolls up.
3. **Thinking bar** (`#thinking`, a single-line Static): shown only while the LLM is streaming (see [Streaming LLM](#streaming-llm)).
4. **Input area** (`#input`, a multi-line TextArea with a highlighted border): Enter to send, Shift+Enter for a newline.
5. **Footer**: `Enter send · Shift+Enter newline · PgUp/PgDn scroll · /exit quit`.

### Streaming LLM

LLM replies are read as a stream, with three states:

- **Waiting for the first token**: the thinking bar shows `✦ Thinking ⣾ Organizing thoughts…`, avoiding a blank line that might look like a hang.
- **Streaming**: the thinking bar shows `✦ Thinking ⣾ …<stream tail>▍`, refreshing one spinner frame (braille animation) every 100ms. The tail is truncated by display width (CJK characters occupy 2 columns). Reasoning deltas are shown first; otherwise content deltas are shown.
- **Done**: the thinking bar hides, and the full reply is written to the chat history area prefixed with `🤖 Assistant:`.

Tool-calling iterations also stream: before each tool round the "Organizing thoughts…" placeholder is shown, then after the stream ends the tools execute and the next streaming round begins, until the LLM returns no more tool calls. The opening prompt at each stage entry is also generated as a stream: `anappt run` mode injects `conv.opening_instruction`, and `anappt interactive` mode injects `conv.opening_instruction_interactive`.

## Available Meta-commands

Type a meta-command in the input area starting with `/` (case-insensitive). The system recognizes these 6 meta-commands:

| Meta-command | Description |
|--------------|-------------|
| `/confirm` | Validate the current stage's `is_ready`; advance to the next stage if ready, reject if not |
| `/exit` | Generate session core summary → decide whether to update project memory → Git commit → exit |
| `/status` | Print the status table for all stages |
| `/memory` | Print the project memory (contents of `.anappt/memory.md`) |
| `/help` | List available meta-commands |
| `/ppt <requirement>` | Skip the S1–S5 prep stages and generate a PPT directly via dashi-ppt-skill (see [`/ppt` Direct Generation](#ppt-direct-generation)) |

!!! info "Why the `/` prefix is required"
    Meta-commands must start with `/` so they are unambiguous from free text in any locale (in English, bare words like `confirm`/`exit` are easily confused with conversation content). The legacy bare words (`confirm`/`exit`/`help`/`quit`) and Chinese aliases (`退出`/`帮助`) **have been removed**.

    - Input that starts with `/` but whose first token is not a known meta-command (e.g. `/foo bar`) **is treated as free text** and enters the LLM conversation.
    - Input that does not start with `/` is also treated as free text.

## Meta-command Details

### `/confirm`

Validates the current stage's `is_ready` gate: if outputs are ready, advances the stage to `completed`, saves state, triggers a Git commit, then enters the next stage (or exits if the pipeline is complete); if not ready, prints a rejection notice and returns. The LLM cannot self-advance.

```
> /confirm
Stage S1 confirmed and advanced.
(LLM streams the S2 stage opening)
>
```

### `/status`

Prints all stage statuses as a table (written to the chat history area):

```
> /status
Current pipeline status:
ID | Name                | Status          | Iter
---+---------------------+-----------------+-----
S1 | Topic & Goal Definition | completed       | 1
S2 | Data Requirement Analysis | completed       | 1
S3 | Data Loading & Validation | completed       | 1
S4 | Data Analysis       | awaiting_review | 2
S5 | Report Generation   | pending         | 0
S6 | PPT Generation      | pending         | 0
```

### `/memory`

Prints the full contents of the project memory file `.anappt/memory.md`. If memory is empty, a placeholder notice is printed. See [Project Memory](#project-memory).

```
> /memory
(full contents of .anappt/memory.md)
```

### `/help`

Lists available meta-commands:

```
> /help
Meta-commands (/ prefix): /confirm (advance) /status (show status) /memory (show memory) /help (help) /exit (quit) /ppt <requirement> (direct PPT). Other input goes to the LLM as conversation.
```

### `/exit`

Exits the conversation loop, executing the following steps in sequence (each best-effort):

1. Calls the LLM to generate a core summary for the current session
2. Flushes the session log to disk
3. Calls the LLM to decide whether the project memory needs updating (update if there is progress, leave untouched if not)
4. Triggers the `commit_on_exit` Git commit

```
> /exit
(generates session summary, updates memory, Git commit)
```

## `/ppt` Direct Generation

`/ppt <requirement>` is an independent direct PPT-generation command: it skips the S1–S5 prep stages and invokes the dashi-ppt-skill to generate a PPT directly.

- **Usage**: `/ppt Generate a 10-slide deck on Q3 mobile user growth` (state the PPT requirement after `/ppt`, separated by a space; an empty requirement prints usage and returns).
- **Behavior**: loads the dashi-ppt `SKILL.md` as the LLM system prompt, temporarily enables the S6 stage tool subset (see the S6 row in [Per-stage tools](#llm-tool-system); includes `read_file` / `write_artifact` / `render_deck` / `export_pptx`, etc.), and runs one streaming LLM turn (with tool-calling iterations) using the user requirement as the user message. This drives the LLM to construct `output/ppt/goal.json` and call `render_deck` to render `output/ppt/presentation.html`. `final_report.md` is **not required**.
- **Does not affect the gated pipeline**: this command does not change the stage state in `state.yaml` and does not write to the main conversation history `self.messages` — it is an independent side-generation. The requirement and the LLM reply are logged to the current session log.
- **Skill not installed**: prompts the user to run `anappt setup` to install; no LLM call is made.
- **On completion**: tells the user to review the result in the browser; to adjust, keep chatting; when satisfied, type `/exit` to quit.

```
> /ppt Generate a 10-slide deck on Q3 mobile user growth
(thinking bar streams the LLM constructing goal.json and calling render_deck)
PPT generated. Please review it in the browser. To adjust, keep chatting; when satisfied, type /exit to quit.
```

## Free-text Conversation

Any text in the input area that does not start with `/` enters the LLM conversation as a user message (carrying the cross-turn persistent conversation history) and is written to the chat history area prefixed with `👤 You:`. The LLM responds with context awareness (streamed, then written prefixed with `🤖 Assistant:` once complete) and may call the current stage's authorized tool subset to perform real operations (e.g., read/write artifacts, execute analysis code, search for information).

```
> The topic should focus more on mobile user growth
(LLM streams its reply, calls write_artifact to update report.yaml / s1_topic.md, then writes to the chat area)
> The data requirements need to include user retention metrics
(LLM updates s2_data_requirement.md and replies)
```

Conversation history persists across turns within the same stage; when the user `/confirm`s advancement to the next stage, the history is cleared and starts fresh.

## LLM Tool System

The LLM can call the following 10 tools during conversation to perform real operations. Each stage enables only its authorized subset; unauthorized tool calls are rejected by the system.

| Tool | Description |
|------|-------------|
| `read_file` | Read a file's contents from the project directory (UTF-8) |
| `write_artifact` | Write a stage artifact (parent directories auto-created) |
| `read_memory` | Read the project memory (`.anappt/memory.md`) |
| `read_history` | Read past session-history documents by stage ID / date / all |
| `list_stage_artifacts` | List a stage's declared artifacts and whether each exists |
| `execute_python` | Execute Python code in a sandbox (network blocked; file access limited to `data/` and `output/`) |
| `search_web` | Web search (returns title, URL, snippet) |
| `fetch_url` | Read a web page as Markdown (requires `JINA_API_KEY`) |
| `render_deck` | Render PPT HTML (via dashi-ppt-skill) |
| `export_pptx` | Export PPTX (or PDF) |

Per-stage enabled tool subsets:

| Stage | Enabled tools |
|-------|---------------|
| S1 Topic & Goal Definition | `read_file` / `write_artifact` / `read_memory` / `read_history` |
| S2 Data Requirement Analysis | `read_file` / `write_artifact` / `read_memory` / `read_history` |
| S3 Data Loading & Validation | `read_file` / `write_artifact` / `execute_python` / `read_memory` / `read_history` |
| S4 Data Analysis | `read_file` / `write_artifact` / `execute_python` / `search_web` / `fetch_url` / `read_memory` / `read_history` |
| S5 Report Generation | `read_file` / `write_artifact` / `read_memory` / `read_history` |
| S6 PPT Generation | `read_file` / `write_artifact` / `render_deck` / `export_pptx` / `read_memory` / `read_history` |

## Stage Artifacts

The authoritative artifact paths for each stage (written by the `write_artifact` tool) are:

| Stage | Artifact path |
|-------|---------------|
| S1 | `report.yaml` (project root) + `.anappt/s1_topic.md` |
| S2 | `.anappt/s2_data_requirement.md` |
| S3 | `.anappt/s3_data_profile.md` |
| S4 | `.anappt/s4_analysis_report.md` |
| S5 | `output/final_report.md` |
| S6 | `output/ppt/goal.json` + `output/ppt/presentation.html` (+ optional `output/ppt/presentation.pptx`) |

On `/confirm`, the system validates whether the current stage's artifacts are ready via `is_ready` (typically checks file existence and non-emptiness).

## Session Logging

Each stage's conversation is automatically logged to the `.anappt/session_history/` directory. Filenames follow `YYYY-MM-DD_<stage>.md` (UTC date), e.g. `2024-12-01_S1.md`.

Each log file is structured as:

```markdown
## Core Summary
(LLM-generated 1-3 sentence summary at session exit)

### Dialog Record

## Agent

[2024-12-01T10:30:00Z]

(LLM reply content)

## User

[2024-12-01T10:30:15Z]

(user input content)
```

- **Same-day same-stage** sessions are appended to the same file separated by `---`, rather than overwritten.
- The **core summary** is generated by the LLM at `/exit` for the currently buffered session and placed at the top of that session block.
- Session logs are excluded from Git tracking by default (via `.gitignore`).

## Project Memory

The project memory is stored in `.anappt/memory.md`, maintained by `MemoryManager`. It is a cross-session persistent record of project progress, key decisions, and important context.

- **Read**: The LLM can read it at any time via the `read_memory` tool; the current memory content is also auto-injected into the system prompt.
- **Update**: Only at session exit (`/exit`), the LLM decides whether the current session produced anything worth recording:
    - Has progress → The LLM outputs the full updated `memory.md` content (preserving existing timestamps, appending new dated entries with `YYYY-MM-DD`).
    - No progress → The LLM outputs `NO_UPDATE` and the file is left untouched.
- The user can view the current memory contents via the `/memory` meta-command.

## On-demand History Reading

The LLM can read past session documents under `.anappt/session_history/` on demand via the `read_history` tool. The `target` parameter supports:

| `target` value | Match scope |
|----------------|-------------|
| `all` (default) | All `*.md` files in the directory |
| `YYYY-MM-DD` (date) | Files whose names start with that date |
| Stage ID (e.g. `S4`) | Files whose stage segment equals that ID (e.g. `2024-12-01_S4.md`) |

Matched file contents are sorted by filename and concatenated with `---` separators. This allows the LLM to review past session dialogs and core summaries to provide context for the current stage.

In `anappt interactive` mode, the system prompt also injects a filename index of recent session history (up to 20 entries, reverse-sorted by name), helping the LLM become aware of what history is available to read.

## Git Auto-Commit

In conversation mode, Git auto-commits trigger at three points:

| Trigger | Commit message format |
|---------|----------------------|
| Stage output completed | `feat(S1): complete Topic & Goal Definition - <files>` |
| User `/confirm` advance | `feat(S1): confirm Topic & Goal Definition` |
| Exit (`/exit`) | `chore: auto-save on exit` |

Commit messages are localized via `t()`. If the project directory is not a Git repository, all commit operations are silently skipped. The session history directory (`.anappt/session_history/`) is excluded from commits.

## Usage Examples

### Complete Conversational Flow

```bash
# 1. Create project
anappt new my_report
cd my_report

# 2. Place data
cp ~/data.csv data/

# 3. Start the conversational TUI
anappt interactive

# 4. Conversation:
# (LLM streams the opening: detects report.yaml is not yet filled in, prompts to confirm topic direction)
> I want to analyze mobile user growth trends, audience is the product team
# (LLM streams its reply, calls write_artifact to write report.yaml and .anappt/s1_topic.md, replies with confirmation)
> /confirm
# Stage S1 confirmed and advanced.
# (LLM streams the S2 opening: analyzes data requirements based on S1 topic)
> Need to add user retention and activity metrics
# (LLM updates s2_data_requirement.md)
> /confirm
# Stage S2 confirmed and advanced.
# (LLM streams the S3 opening: calls execute_python to scan data/ and produce a data profile)
> /confirm
# Stage S3 confirmed and advanced.
# (LLM streams the S4 opening: calls execute_python to analyze data)
> Please add monthly trend analysis
# (LLM calls execute_python to run analysis, updates s4_analysis_report.md)
> /confirm
# Stage S4 confirmed and advanced.
# (LLM streams the S5 opening: writes the analysis report)
> /confirm
# Stage S5 confirmed and advanced. Report generated at output/final_report.md
# (LLM streams the S6 opening: constructs goal.json and renders PPT)
> /confirm
# Stage S6 confirmed and advanced. All stages complete. Project delivered.
> /exit
# (generates session summary, updates memory, Git commit, exits)
```

### `/ppt` Direct Generation

```bash
anappt run
# (LLM streams the opening)
> /ppt Generate a 10-slide deck on Q3 mobile user growth
# (thinking bar streams the LLM constructing goal.json and calling render_deck)
# PPT generated. Please review it in the browser. To adjust, keep chatting; when satisfied, type /exit to quit.
> /exit
```

### Mid-Session Exit and Resume

```bash
# First run, exit after reaching S4
anappt run
# (LLM streams the opening: currently at S4, outputs not ready yet)
> /exit
# (session summary written, Git commit)

# Second run — both run and interactive can resume
anappt run
# (LLM streams the opening: reads state, finds S4 in progress, prompts to continue analysis)
> /status
# S4 | Data Analysis | in_progress | 1
# (continue S4 conversation)
> /confirm
# Stage S4 confirmed and advanced.
```
