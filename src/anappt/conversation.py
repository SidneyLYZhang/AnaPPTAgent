"""Unified conversation-driven TUI engine for AnaPPTAgent (Task C1).

``ConversationRunner`` is the single dialog loop shared by ``anappt run``
and ``anappt interactive``. It drives a multi-turn conversation between
the LLM and the user: at each stage entry the LLM produces an opening
analysis of progress + next step, then the user replies with either a
meta-command (``confirm`` / ``exit`` / ``status`` / ``memory`` / ``help``)
or free text that flows back into the LLM with the running message
history. The LLM can call a registered tool (read_file, write_artifact,
execute_python, search_web, fetch_url, render_deck, export_pptx,
read_history, read_memory, list_stage_artifacts) to perform real work
inside the project directory.

Gating is human-controlled: only the ``confirm`` meta-command (after the
current stage's ``is_ready`` check passes) advances the stage to
``completed`` and moves ``current_stage`` forward. The LLM is explicitly
told it MUST NOT self-advance.

Stage lookup goes through :func:`anappt.stages.build_stage_registry`
(the canonical id→StageBase map), so this module does not need to import
the orchestrator.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anappt.i18n import t
from anappt.io.state import StageStatus
from anappt.llm.models import ModelRole
from anappt.llm.provider import AnaPPTLLM
from anappt.stage_base import StageBase
from anappt.stages import build_stage_registry
from anappt.tools.agent_loop import ToolDef
from anappt.types import InteractiveUIProtocol, PipelineContext, model_role_for_stage

# --- Module-level Chinese system-prompt constants ---------------------------
# Per the spec, LLM system-prompt text may be hard-coded Chinese; only
# user-visible UI strings go through ``t()``.

BASE_ROLE = (
    "你是 AnaPPTAgent 分析助手,通过对话驱动一个六阶段(S1-S6)分析报告与 PPT "
    "生成流水线。你与用户在同一对话循环中协作:你分析当前阶段进展、按需调用工具"
    "完成实际操作(读写产出物、执行 Python、Web 搜索/读取、dashi-ppt 渲染/导出、"
    "读取历史、更新记忆),并引导用户在产出就绪后通过 ``confirm`` 元命令确认推进。"
    "你的回复应当信息密集、可操作,避免空泛复述。"
)

GATE_RULES = (
    "## 门控规则(严格)\n"
    "- 你不可自行推进阶段;阶段状态转换只能由用户输入 ``confirm`` 元命令触发,"
    "且系统会校验当前阶段产出是否就绪。\n"
    "- 在用户输入 ``confirm`` 前,你不得宣告阶段已完成,也不得假定下一阶段已开始。\n"
    "- 用户提出修改意见时,你应根据反馈更新产出物后再次请用户确认。\n"
    "- 你只能调用本阶段已授权的工具子集;未授权的工具调用会被系统拒绝。"
)

RUN_DIRECTIVE = (
    "## 运行模式指令\n"
    "当前为 ``anappt run`` 模式。请聚焦当前阶段,提示用户下一步以恢复门控流水线:"
    "若产出尚未就绪,说明还缺什么;若产出已就绪,明确提示用户输入 ``confirm`` 推进。"
)

INTERACTIVE_DIRECTIVE = (
    "## 交互模式指令\n"
    "当前为 ``anappt interactive`` 模式。请综合以上信息(全部阶段状态、项目记忆、"
    "近期会话历史索引、当前产出物清单)自识别用户现在需要做的事情,并主动提示用户。"
    "你可以跨越阶段提供建议,但仍不可自行推进阶段。"
)


class ConversationRunner:
    """Unified LLM-user conversation loop shared by run/interactive.

    Drives multi-turn dialog with cross-turn message history. The LLM
    gets a system prompt built from the current stage's declarative
    interface (goal / artifacts / system_prompt_fragment / tools /
    is_ready) plus pipeline progress + project memory, and may invoke a
    subset of registered tools per turn.

    Attributes:
        ctx: Pipeline context (project_dir/config/llm/state/ui/session/
            git/output_dir/skill_manager/memory).
        mode: ``"run"`` or ``"interactive"`` — controls system prompt
            extras (history index + artifacts listing in interactive).
        ui: Interactive UI protocol implementation.
        max_iterations: Max tool-calling iterations within a single LLM
            turn before falling back to a plain chat call.
        messages: Cross-turn persistent conversation history (only
            user/assistant text turns; tool exchanges are scoped to
            ``_llm_call`` and not retained across user turns).
    """

    def __init__(
        self,
        ctx: PipelineContext,
        mode: str,
        ui: InteractiveUIProtocol,
        max_iterations: int = 12,
    ) -> None:
        """Initialize the conversation runner.

        Args:
            ctx: Pipeline context with all services.
            mode: Either ``"run"`` or ``"interactive"``.
            ui: UI implementation satisfying InteractiveUIProtocol.
            max_iterations: Max tool-calling rounds per LLM turn.
        """
        if mode not in ("run", "interactive"):
            raise ValueError(f"Invalid mode: {mode!r}. Must be 'run' or 'interactive'.")
        self.ctx: PipelineContext = ctx
        self.mode: str = mode
        self.ui: InteractiveUIProtocol = ui
        self.max_iterations: int = max_iterations
        self.messages: list[dict[str, str]] = []
        self._exit: bool = False
        # Lazily-built stage registry (id → StageBase instance).
        self._stage_registry: dict[str, StageBase] = build_stage_registry()
        # Lazily-built tool registry (name → (ToolDef, callable)) for
        # the current stage. Rebuilt when the stage changes.
        self._tools: dict[str, tuple[ToolDef, Any]] = {}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the conversation loop until the user exits.

        Enters the current stage (pending→in_progress + new session),
        produces the LLM opening, then reads user input in a loop:
        meta-commands are dispatched locally; free text enters the LLM
        turn. On exit, finalizes the session summary + memory + git.
        """
        self._enter_stage()
        self._opening()
        while not self._exit:
            raw = self.ui.input(t("conv.prompt"))
            if raw is None:  # EOF — treat as exit
                break
            text = raw.strip()
            if not text:
                continue
            if self._handle_meta(text):
                continue
            self._turn(text)
        self._finalize()

    # ------------------------------------------------------------------
    # Stage helpers
    # ------------------------------------------------------------------

    def _stage_obj(self) -> StageBase | None:
        """Return the StageBase instance for the current stage id.

        Returns:
            StageBase instance, or ``None`` if the pipeline is complete
            or the stage id is unknown.
        """
        cur = self.ctx.state.get_current_stage()
        if cur is None:
            return None
        return self._stage_registry.get(cur.id)

    def _enter_stage(self) -> None:
        """Enter the current stage: pending→in_progress + new session.

        If the current stage is already in_progress/awaiting_review (a
        resumed session), only the session log is reset — no transition
        is attempted. Tool registry is rebuilt for the new stage.
        """
        cur = self.ctx.state.get_current_stage()
        if cur is None:
            return
        if cur.status == StageStatus.PENDING:
            self.ctx.state.transition(cur.id, StageStatus.IN_PROGRESS)
        if self.ctx.session is not None:
            self.ctx.session.new_session(cur.id)
        # Rebuild tool registry for this stage.
        stage = self._stage_obj()
        if stage is not None:
            self._tools = self._build_tools(stage)

    # ------------------------------------------------------------------
    # System prompt construction
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the current LLM call.

        Combines BASE_ROLE + stage id/name/status + stage goal + stage
        system_prompt_fragment + pipeline progress + project memory +
        tool descriptions + gate rules, plus (interactive) history
        index + artifacts listing + INTERACTIVE_DIRECTIVE, or
        RUN_DIRECTIVE for run mode.

        Returns:
            Assembled system prompt string.
        """
        stage = self._stage_obj()
        cur = self.ctx.state.get_current_stage()
        if cur is None or stage is None:
            # Pipeline complete — minimal prompt.
            return "\n\n".join([
                BASE_ROLE,
                "## 流水线已完成\n所有阶段均已 completed,无待办事项。",
                GATE_RULES,
            ])

        parts: list[str] = [
            BASE_ROLE,
            (
                f"## 当前阶段:{cur.id}({t(cur.name)})— 状态:{cur.status.value}"
            ),
            f"### 阶段目标:{t(stage.goal)}",
            stage.system_prompt_fragment(self.ctx),
            (
                "## 阶段进展\n"
                + "\n".join(
                    f"- {s.id} {s.name}: {s.status.value}"
                    for s in self.ctx.state.get_all_stages()
                )
            ),
            f"## 项目记忆\n{self.ctx.memory.read() or t('conv.memory_empty')}",
            "## 可用工具\n" + self._tool_descriptions(stage),
            GATE_RULES,
        ]

        if self.mode == "interactive":
            parts.append("## 历史会话索引\n" + self._history_index())
            parts.append("## 当前产出物\n" + self._artifacts_listing())
            parts.append(INTERACTIVE_DIRECTIVE)
        else:
            parts.append(RUN_DIRECTIVE)

        return "\n\n".join(parts)

    def _history_index(self) -> str:
        """Return a short index of past session-history files.

        Lists filenames under ``.anappt/session_history/`` (most recent
        first), truncated to a reasonable cap. Used only in interactive
        mode to give the LLM awareness of past sessions.

        Returns:
            Newline-joined filename list, or a placeholder when empty.
        """
        session_dir = self.ctx.project_dir / ".anappt" / "session_history"
        if not session_dir.is_dir():
            return "(无历史会话)"
        try:
            files = sorted(
                (p.name for p in session_dir.iterdir() if p.is_file()),
                reverse=True,
            )
        except OSError:
            return "(无历史会话)"
        if not files:
            return "(无历史会话)"
        # Cap to 20 entries to keep the system prompt bounded.
        capped = files[:20]
        return "\n".join(capped) + (f"\n...(共 {len(files)} 个文件)" if len(files) > 20 else "")

    def _artifacts_listing(self) -> str:
        """Return a listing of all stages' declared artifacts + existence.

        Returns:
            Multi-line string; one bullet per stage listing its
            artifacts with existence markers.
        """
        lines: list[str] = []
        for stage_id, stage in self._stage_registry.items():
            artifacts = stage.get_artifacts(self.ctx)
            if not artifacts:
                lines.append(f"- {stage_id}: (无声明产出物)")
                continue
            entries = []
            for rel in artifacts:
                exists = (self.ctx.project_dir / rel).exists()
                entries.append(f"{rel}({'已存在' if exists else '未生成'})")
            lines.append(f"- {stage_id}: " + ", ".join(entries))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LLM call + tool dispatch
    # ------------------------------------------------------------------

    def _opening(self) -> None:
        """Have the LLM produce the opening message for the current stage.

        Appends an instruction user-message, calls the LLM, prints and
        logs the response, then records the assistant turn.
        """
        instr_key = (
            "conv.opening_instruction_interactive"
            if self.mode == "interactive"
            else "conv.opening_instruction"
        )
        self.messages.append({"role": "user", "content": t(instr_key)})
        text = self._llm_call()
        self.ui.print(text)
        if self.ctx.session is not None:
            self.ctx.session.log_agent(text)
        self.messages.append({"role": "assistant", "content": text})

    def _turn(self, user_text: str) -> None:
        """Process one free-text user turn through the LLM.

        Args:
            user_text: The user's free-text input (already stripped).
        """
        if self.ctx.session is not None:
            self.ctx.session.log_user(user_text)
        self.messages.append({"role": "user", "content": user_text})
        text = self._llm_call()
        self.ui.print(text)
        if self.ctx.session is not None:
            self.ctx.session.log_agent(text)
        self.messages.append({"role": "assistant", "content": text})

    def _llm_call(self) -> str:
        """Invoke the LLM for the current turn with tool-calling support.

        Builds the system prompt + running messages, then iterates:
        if the LLM returns tool_calls, execute them and feed results
        back; otherwise return the content. Falls back to a plain
        ``chat`` call when max_iterations is exhausted.

        Returns:
            The final text response from the LLM.
        """
        role: ModelRole = model_role_for_stage(self.ctx.state.state.current_stage)
        sys_prompt = self._build_system_prompt()
        tool_schemas = self._tool_schemas()
        # Build a per-turn working message list: system + persisted
        # user/assistant history. Tool exchanges live only inside this
        # list and are discarded after the turn (self.messages retains
        # only the user/assistant text turns).
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": sys_prompt}
        ] + list(self.messages)

        if not tool_schemas:
            return self.ctx.llm.chat(role, messages)

        for _ in range(self.max_iterations):
            resp = self.ctx.llm.chat_with_tools(role, messages, tool_schemas)
            calls = resp.get("tool_calls", []) or []
            content = resp.get("content", "") or ""
            if not calls:
                return content
            # Rebuild assistant message with tool_calls (litellm/OpenAI format).
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": c["arguments"],
                        },
                    }
                    for c in calls
                ],
            })
            for c in calls:
                result = self._execute_tool(c["name"], c["arguments"])
                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": c["id"],
                    "name": c["name"],
                })
        # Max iterations exhausted — fall back to a plain chat call.
        return self.ctx.llm.chat(role, messages)

    # ------------------------------------------------------------------
    # Meta-command dispatch
    # ------------------------------------------------------------------

    def _handle_meta(self, text: str) -> bool:
        """Dispatch a meta-command. Returns True if ``text`` was handled.

        Recognized commands (case-insensitive):
            exit / quit / 退出 — set the exit flag.
            confirm            — advance the current stage if is_ready.
            status             — print the pipeline status table.
            memory             — print the project memory.
            help / 帮助        — print the help text.

        Args:
            text: The user's input (already stripped).

        Returns:
            True if ``text`` was a meta-command, False otherwise.
        """
        low = text.lower()
        if low in ("exit", "quit", "退出"):
            self._exit = True
            return True
        if low == "confirm":
            self._confirm()
            return True
        if low == "status":
            self._show_status()
            return True
        if low == "memory":
            mem = self.ctx.memory.read() if self.ctx.memory else ""
            self.ui.print(mem or t("conv.memory_empty"))
            return True
        if low in ("help", "帮助"):
            self._show_help()
            return True
        return False

    def _confirm(self) -> None:
        """Handle the ``confirm`` meta-command.

        Checks the current stage's ``is_ready``; if not ready, prints a
        notice and returns. If ready, transitions in_progress →
        awaiting_review → completed (the state machine does not allow
        in_progress → completed directly), saves state, fires the git
        commit hook, and either exits (pipeline complete) or enters the
        next stage with a fresh opening.
        """
        stage = self._stage_obj()
        cur = self.ctx.state.get_current_stage()
        if stage is None or cur is None:
            self.ui.print(t("conv.not_ready"))
            return
        if not stage.is_ready(self.ctx):
            self.ui.print(t("conv.not_ready"))
            return

        # State machine: IN_PROGRESS→AWAITING_REVIEW→COMPLETED (no skips).
        if cur.status == StageStatus.IN_PROGRESS:
            self.ctx.state.transition(cur.id, StageStatus.AWAITING_REVIEW)
            # Re-fetch because transition() mutates the StageState in place.
            cur = self.ctx.state.get_current_stage()
        if cur is not None and cur.status in (
            StageStatus.AWAITING_REVIEW,
            StageStatus.IN_PROGRESS,
        ):
            self.ctx.state.transition(cur.id, StageStatus.COMPLETED)

        self.ctx.state.save()
        if self.ctx.git is not None:
            self.ctx.git.commit_on_confirm(cur.id, t(cur.name))
        self.ui.print(t("conv.stage_confirmed", stage=cur.id))

        if self.ctx.state.is_pipeline_complete():
            self.ui.print(t("conv.project_complete"))
            self._exit = True
            return

        # Enter the next stage with a fresh conversation history.
        self.messages = []
        self._enter_stage()
        self._opening()

    def _show_status(self) -> None:
        """Print the pipeline status as a table."""
        self.ui.print(t("conv.status_header"))
        stages = self.ctx.state.get_all_stages()
        rows = [[s.id, t(s.name), s.status.value, str(s.iteration)] for s in stages]
        self.ui.table(["ID", "Name", "Status", "Iter"], rows)

    def _show_help(self) -> None:
        """Print the help text."""
        self.ui.print(t("conv.help_text"))

    # ------------------------------------------------------------------
    # Finalization (exit)
    # ------------------------------------------------------------------

    def _finalize(self) -> None:
        """Finalize the conversation on exit.

        Generates the session core summary, flushes the session log to
        disk, asks the LLM whether memory needs updating, and fires the
        git commit-on-exit hook. All steps are best-effort: exceptions
        are swallowed so a failure in one step does not block the
        others.
        """
        role: ModelRole = model_role_for_stage(self.ctx.state.state.current_stage)
        if self.ctx.session is not None:
            try:
                self.ctx.session.finalize_summary(self.ctx.llm, role)
            except Exception:
                pass
            try:
                self.ctx.session.flush()
            except Exception:
                pass
        if self.ctx.memory is not None:
            try:
                if self.ctx.session is not None:
                    self.ctx.memory.update(
                        self.ctx.llm, role, self.ctx.session.get_full_text()
                    )
            except Exception:
                pass
        if self.ctx.git is not None:
            try:
                self.ctx.git.commit_on_exit()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Tool registry
    # ------------------------------------------------------------------

    def _tool_schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI function-calling schemas for the active tools.

        Returns:
            List of tool schema dicts (one per active ToolDef).
        """
        schemas: list[dict[str, Any]] = []
        for tool_def, _ in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool_def.name,
                    "description": tool_def.description,
                    "parameters": tool_def.parameters
                    or {"type": "object", "properties": {}},
                },
            })
        return schemas

    def _tool_descriptions(self, stage: StageBase) -> str:
        """Return a textual listing of the stage's enabled tools.

        Args:
            stage: The current StageBase instance.

        Returns:
            Multi-line string; one bullet per enabled tool. The list is
            rebuilt from ``stage.tools(ctx)`` so it reflects the stage's
            declared subset even before ``_enter_stage`` has run.
        """
        enabled = set(stage.tools(self.ctx))
        # Always rebuild from the full registry so descriptions stay in
        # sync with the latest tool definitions.
        all_tools = self._build_tool_defs()
        lines: list[str] = []
        for name in sorted(enabled):
            if name in all_tools:
                td = all_tools[name]
                lines.append(f"- {name}: {td.description}")
        return "\n".join(lines) if lines else "(无)"

    def _execute_tool(self, name: str, arguments_json: str) -> str:
        """Execute a tool call and return a string result.

        Args:
            name: Tool name (must be in the active registry).
            arguments_json: JSON-encoded arguments from the LLM.

        Returns:
            The tool's output as a string. On unknown tool or
            argument-parse error, returns an error string.
        """
        entry = self._tools.get(name)
        if entry is None:
            return f"Error: unknown tool {name!r} (not enabled for this stage)"
        _tool_def, func = entry
        try:
            arguments = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError as e:
            return f"Error: invalid JSON arguments for {name}: {e}"
        if not isinstance(arguments, dict):
            return f"Error: arguments for {name} must be a JSON object"
        try:
            result = func(**arguments)
            return str(result)
        except Exception as e:
            return f"Error: tool {name} failed: {e}"

    def _build_tools(self, stage: StageBase) -> dict[str, tuple[ToolDef, Any]]:
        """Build the active tool registry for the given stage.

        Combines all tool definitions with their bound callables, then
        filters to the stage's declared subset.

        Args:
            stage: The current StageBase instance.

        Returns:
            Dict mapping enabled tool names to (ToolDef, callable) pairs.
        """
        all_defs = self._build_tool_defs()
        all_funcs = self._build_tool_funcs()
        enabled = set(stage.tools(self.ctx))
        registry: dict[str, tuple[ToolDef, Any]] = {}
        for name in enabled:
            if name in all_defs and name in all_funcs:
                registry[name] = (all_defs[name], all_funcs[name])
        return registry

    def _build_tool_defs(self) -> dict[str, ToolDef]:
        """Return all tool definitions keyed by name.

        Returns:
            Dict mapping canonical tool names to ToolDef instances.
        """
        return {
            "read_file": ToolDef(
                name="read_file",
                description=(
                    "Read a file from the project directory. Returns the "
                    "file content (UTF-8). Use relative paths from the "
                    "project root (e.g. 'report.yaml', "
                    "'.anappt/s1_topic.md', 'data/README.md')."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "rel_path": {
                            "type": "string",
                            "description": "Path relative to project root.",
                        },
                    },
                    "required": ["rel_path"],
                },
            ),
            "write_artifact": ToolDef(
                name="write_artifact",
                description=(
                    "Write an artifact file under the project directory. "
                    "Parent directories are created automatically. Use "
                    "relative paths from the project root (e.g. "
                    "'report.yaml', '.anappt/s4_analysis_report.md', "
                    "'output/final_report.md', 'output/ppt/goal.json')."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "rel_path": {
                            "type": "string",
                            "description": "Path relative to project root.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Full text content to write.",
                        },
                    },
                    "required": ["rel_path", "content"],
                },
            ),
            "read_memory": ToolDef(
                name="read_memory",
                description=(
                    "Read the current project memory (.anappt/memory.md). "
                    "Returns the full memory text."
                ),
                parameters={"type": "object", "properties": {}},
            ),
            "read_history": ToolDef(
                name="read_history",
                description=(
                    "Read past session-history documents from "
                    ".anappt/session_history/. Pass target='all' for "
                    "every file, a date 'YYYY-MM-DD' for files from "
                    "that date, or a stage id (e.g. 'S4') for files "
                    "from that stage."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "'all', 'YYYY-MM-DD', or stage id.",
                            "default": "all",
                        },
                    },
                },
            ),
            "list_stage_artifacts": ToolDef(
                name="list_stage_artifacts",
                description=(
                    "List a stage's declared artifact paths and whether "
                    "each exists on disk. Useful for checking readiness "
                    "and for referencing prior outputs."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "stage_id": {
                            "type": "string",
                            "description": "Stage id (e.g. 'S1', 'S4').",
                        },
                    },
                    "required": ["stage_id"],
                },
            ),
            "execute_python": ToolDef(
                name="execute_python",
                description=(
                    "Execute Python code in a sandboxed subprocess. "
                    "Network is blocked; file access is restricted to "
                    "the project data/ and output/ directories plus a "
                    "temp dir. Returns stdout, stderr, and return code."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python source code to execute.",
                        },
                    },
                    "required": ["code"],
                },
            ),
            "search_web": ToolDef(
                name="search_web",
                description=(
                    "Search the web for information. Returns a list of "
                    "results with title, url, and snippet."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string.",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Max results (default 5).",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            ),
            "fetch_url": ToolDef(
                name="fetch_url",
                description=(
                    "Fetch and read the content of a web page (via Jina "
                    "Reader). Returns Markdown content. Requires "
                    "JINA_API_KEY to be configured."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to fetch.",
                        },
                    },
                    "required": ["url"],
                },
            ),
            "render_deck": ToolDef(
                name="render_deck",
                description=(
                    "Render a dashi-ppt goal.json to an HTML deck via "
                    "the dashi-ppt-skill. Both paths are relative to "
                    "the project root."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "goal_json_path": {
                            "type": "string",
                            "description": "Relative path to goal.json.",
                        },
                        "output_html_path": {
                            "type": "string",
                            "description": "Relative path for the output HTML.",
                        },
                    },
                    "required": ["goal_json_path", "output_html_path"],
                },
            ),
            "export_pptx": ToolDef(
                name="export_pptx",
                description=(
                    "Export a rendered dashi-ppt deck to PPTX (or PDF). "
                    "Paths are relative to the project root."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "deck_dir": {
                            "type": "string",
                            "description": "Relative path to the rendered deck directory.",
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Relative path for the exported file.",
                        },
                        "format": {
                            "type": "string",
                            "description": "Export format: 'pptx' (default) or 'pdf'.",
                            "default": "pptx",
                            "enum": ["pptx", "pdf"],
                        },
                    },
                    "required": ["deck_dir", "output_file"],
                },
            ),
        }

    def _build_tool_funcs(self) -> dict[str, Any]:
        """Return all tool callables keyed by name, bound to ``self.ctx``.

        Returns:
            Dict mapping canonical tool names to callables. Each
            callable accepts the tool's declared parameters as kwargs.
        """
        ctx = self.ctx
        project_dir = ctx.project_dir
        data_dir = ctx.get_data_dir()
        output_dir = ctx.output_dir

        def read_file(rel_path: str) -> str:
            path = project_dir / rel_path
            if not path.is_file():
                return f"Error: file not found: {rel_path}"
            try:
                return path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Fall back to bytes repr for non-utf8 files.
                return repr(path.read_bytes())

        def write_artifact(rel_path: str, content: str) -> str:
            path = project_dir / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"OK: wrote {len(content)} chars to {rel_path}"

        def read_memory() -> str:
            if ctx.memory is None:
                return "Error: memory manager not available"
            return ctx.memory.read() or "(memory empty)"

        def read_history(target: str = "all") -> str:
            from anappt.io.session import read_history as _read_history

            session_dir = project_dir / ".anappt" / "session_history"
            return _read_history(session_dir, target=target)

        def list_stage_artifacts(stage_id: str) -> str:
            stage = self._stage_registry.get(stage_id)
            if stage is None:
                return f"Error: unknown stage id {stage_id!r}"
            artifacts = stage.get_artifacts(ctx)
            if not artifacts:
                return f"{stage_id}: (no declared artifacts)"
            lines = []
            for rel in artifacts:
                exists = (project_dir / rel).exists()
                lines.append(
                    f"- {rel} ({'exists' if exists else 'missing'})"
                )
            return "\n".join(lines)

        def execute_python(code: str) -> str:
            from anappt.tools.code_exec import execute_python as _exec

            result = _exec(
                code,
                timeout=60,
                allowed_dirs=[str(data_dir), str(output_dir)],
            )
            return (
                f"{result.stdout}"
                f"\n---stderr---\n{result.stderr}"
                f"\nrc={result.returncode}"
            )

        def search_web(query: str, num_results: int = 5) -> str:
            from anappt.tools.web_search import search_web as _search

            try:
                results = _search(query, num_results)
            except Exception as e:
                return f"Error: web search failed: {e}"
            if not results:
                return "(no results)"
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(
                    f"{i}. {r.title}\n   {r.url}\n   {r.snippet}"
                )
            return "\n".join(lines)

        def fetch_url(url: str) -> str:
            from anappt.tools.web_fetch import fetch_url as _fetch

            try:
                content = _fetch(url)
            except Exception as e:
                return f"Error: fetch failed: {e}"
            # Truncate very long pages to keep the LLM context bounded.
            max_len = 8000
            if len(content) > max_len:
                content = content[:max_len] + f"\n...(truncated, total {len(content)} chars)"
            return content

        def render_deck(goal_json_path: str, output_html_path: str) -> str:
            from anappt.bridge.dashi_ppt import DashiPPTBridge

            skill_root = self._get_skill_root()
            if skill_root is None:
                return (
                    "Error: dashi-ppt skill not installed. "
                    "Run 'anappt setup' first."
                )
            try:
                DashiPPTBridge.render_deck(
                    goal_json_path=Path(goal_json_path),
                    output_html_path=Path(output_html_path),
                    skill_root=skill_root,
                )
                return f"OK: rendered {output_html_path}"
            except Exception as e:
                return f"Error: render_deck failed: {e}"

        def export_pptx(
            deck_dir: str, output_file: str, format: str = "pptx"
        ) -> str:
            from anappt.bridge.dashi_ppt import DashiPPTBridge

            skill_root = self._get_skill_root()
            if skill_root is None:
                return (
                    "Error: dashi-ppt skill not installed. "
                    "Run 'anappt setup' first."
                )
            try:
                DashiPPTBridge.export(
                    deck_dir=Path(deck_dir),
                    format=format,
                    output_file=Path(output_file),
                    skill_root=skill_root,
                )
                return f"OK: exported {output_file} ({format})"
            except Exception as e:
                return f"Error: export_pptx failed: {e}"

        return {
            "read_file": read_file,
            "write_artifact": write_artifact,
            "read_memory": read_memory,
            "read_history": read_history,
            "list_stage_artifacts": list_stage_artifacts,
            "execute_python": execute_python,
            "search_web": search_web,
            "fetch_url": fetch_url,
            "render_deck": render_deck,
            "export_pptx": export_pptx,
        }

    def _get_skill_root(self) -> Path | None:
        """Return the dashi-ppt skill root directory, or None if missing.

        Mirrors the lookup logic in S6PPTStage.run(): locate_skill()
        returns the SKILL.md path; the skill root is its parent.

        Returns:
            Path to the skill root, or ``None`` when skill_manager is
            missing or the skill is not installed.
        """
        if self.ctx.skill_manager is None:
            return None
        try:
            skill_md = self.ctx.skill_manager.locate_skill()
        except Exception:
            return None
        if skill_md is None:
            return None
        return Path(skill_md).parent


# Re-export AnaPPTLLM for convenience (callers that build a ConversationRunner
# often also construct the LLM provider in the same scope).
__all__ = ["ConversationRunner", "AnaPPTLLM"]
