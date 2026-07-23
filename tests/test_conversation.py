"""Tests for ConversationRunner (Task C1).

Covers:
  1. Opening turn — LLM produces opening text, ui.print receives it,
     session.log_agent records it.
  2. Free-text turn — user input flows back into LLM; reply is printed
     and logged; ``exit`` exits cleanly.
  3. Tool calling — chat_with_tools returns a tool_call on the first
     iteration and a final text on the second; the tool actually writes
     a file and the final text is shown.
  4. confirm advances the stage when is_ready; transitions
     in_progress → awaiting_review → completed; current_stage moves to
     the next stage; git.commit_on_confirm is invoked.
  5. confirm is rejected when is_ready is False.
  6. exit triggers finalize_summary, flush, memory.update and
     git.commit_on_exit.
  7. interactive-mode system prompt contains history index + artifacts
     listing sections.
  8. read_history tool — given a session_history file, the LLM-invoked
     tool returns its content.
  9. ``/``-prefixed meta-commands (Task 5): ``/confirm`` / ``/exit``
     / ``/status`` (case-insensitive), bare words and unknown ``/foo``
     fall through to the LLM as free text.
 10. StreamingSink integration (Task 4): with a sink injected, the
     runner uses ``chat_stream`` / ``chat_with_tools_stream`` and
     pushes ``thinking_update`` / ``assistant_message`` calls.
 11. ``/ppt <requirement>`` direct generation (Task 6): skill missing,
     skill present (mocked), empty requirement.

The tests use a FakeUI that returns canned input from a queue, plus
MagicMock LLMs with configurable chat / chat_with_tools return values.

Note on LLM call routing: S1 (and most stages) declare a non-empty
``tools(ctx)`` subset, so a turn's first LLM call goes through
``chat_with_tools`` (not ``chat``). The plain ``chat`` method is only
used by ``finalize_summary`` and ``memory.update`` during ``_finalize``,
and as a fallback when no tools are enabled.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anappt import i18n
from anappt.conversation import ConversationRunner
from anappt.io.config import ReportConfig
from anappt.io.memory import MemoryManager
from anappt.io.session import SessionLogger
from anappt.io.state import StateManager
from anappt.types import PipelineContext


@pytest.fixture(autouse=True)
def force_zh_locale():
    """Force zh locale so spec-described Chinese strings are emitted.

    The test environment may otherwise detect ``en`` from LANG/LANGUAGE.
    """
    i18n._reset_cache()
    i18n.set_locale("zh")
    yield
    i18n._reset_cache()


# ---------------------------------------------------------------------------
# A minimal complete report.yaml used to make S1 is_ready.
# ---------------------------------------------------------------------------
COMPLETE_REPORT_YAML = """\
project:
  name: "Test Project"
  type: "one_time"
  created: "2026-07-22"

report:
  topic: "Q3 渠道 ROI 分析"
  motivation: "评估各渠道拉新效率"
  audience:
    - "增长团队"
  objectives:
    - "识别增长瓶颈"
  success_criteria:
    - "结论有数据支撑"

delivery:
  ppt_pages: "15-20"
  formats: ["pptx", "html"]
  theme_preference: null
"""


class FakeUI:
    """In-memory UI mock satisfying InteractiveUIProtocol.

    ``input`` returns successive strings from ``inputs``; once the
    queue is empty it returns ``"/exit"`` to avoid infinite loops.

    Attributes:
        inputs: Queue of user input strings.
        prints: List of all printed messages.
        tables: List of (headers, rows) tuples passed to ``table``.
        confirms: List of confirmation prompts received.
        progress_msgs: List of progress messages received.
    """

    def __init__(self, inputs: list[str] | None = None) -> None:
        self.inputs: list[str] = list(inputs) if inputs else []
        self.prints: list[str] = []
        self.tables: list[tuple[list[str], list[list[str]]]] = []
        self.confirms: list[str] = []
        self.progress_msgs: list[str] = []

    def print(self, message: str) -> None:
        self.prints.append(message)

    def input(self, prompt: str) -> str:
        if self.inputs:
            return self.inputs.pop(0)
        # Safety net: never hang the test loop.
        return "/exit"

    def confirm(self, prompt: str) -> bool:
        self.confirms.append(prompt)
        return True

    def table(
        self, headers: list[str], rows: list[list[str]]
    ) -> None:
        self.tables.append((headers, rows))

    def progress(self, message: str) -> None:
        self.progress_msgs.append(message)


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory layout under tmp_path."""
    p = tmp_path / "proj"
    p.mkdir()
    (p / "data").mkdir()
    (p / "output").mkdir()
    (p / ".anappt").mkdir()
    (p / ".anappt" / "session_history").mkdir()
    return p


@pytest.fixture
def state(project_dir: Path) -> StateManager:
    """Return a StateManager backed by .anappt/state.yaml."""
    return StateManager(project_dir / ".anappt" / "state.yaml")


@pytest.fixture
def session(project_dir: Path) -> SessionLogger:
    """Return a SessionLogger writing under .anappt/session_history."""
    return SessionLogger(project_dir / ".anappt" / "session_history")


@pytest.fixture
def memory(project_dir: Path) -> MemoryManager:
    """Return a MemoryManager backed by .anappt/memory.md (may not exist)."""
    return MemoryManager(project_dir / ".anappt" / "memory.md")


def _make_llm(
    chat_return: str = "Mock LLM opening.",
    chat_with_tools_responses: list[dict] | None = None,
    chat_side_effect: list[str] | None = None,
) -> MagicMock:
    """Build a MagicMock LLM with the given canned responses.

    Args:
        chat_return: Default return value for ``chat`` (used by
            finalize_summary + memory.update). Ignored when
            ``chat_side_effect`` is provided.
        chat_with_tools_responses: If provided, used as the
            ``side_effect`` list for ``chat_with_tools``. Each entry is
            returned in succession.
        chat_side_effect: If provided, used as ``side_effect`` for
            ``chat`` (overrides ``chat_return``).

    Returns:
        Configured MagicMock LLM.
    """
    mock = MagicMock()
    if chat_side_effect is not None:
        mock.chat.side_effect = chat_side_effect
    else:
        mock.chat.return_value = chat_return
    if chat_with_tools_responses is not None:
        mock.chat_with_tools.side_effect = list(chat_with_tools_responses)
    else:
        # Default: no tool calls; return the same text as chat_return.
        mock.chat_with_tools.return_value = {
            "content": chat_return,
            "tool_calls": [],
        }
    return mock


def _build_ctx(
    project_dir: Path,
    state: StateManager,
    session: SessionLogger,
    memory: MemoryManager,
    llm: MagicMock,
    ui: FakeUI,
    git: MagicMock | None = None,
) -> PipelineContext:
    """Build a PipelineContext with the provided services."""
    return PipelineContext(
        project_dir=project_dir,
        config=ReportConfig(),
        llm=llm,
        state=state,
        ui=ui,
        session=session,
        git=git,
        memory=memory,
    )


# ---------------------------------------------------------------------------
# 1. Opening turn
# ---------------------------------------------------------------------------


class TestOpening:
    """LLM produces opening text on stage entry; ui.print + session log."""

    def test_opening_printed_and_logged(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        opening_text = "Hello! Let's start S1."
        llm = _make_llm(
            chat_return="finalize-summary-text",
            chat_with_tools_responses=[
                {"content": opening_text, "tool_calls": []},
            ],
        )
        ui = FakeUI(inputs=[])  # immediately exit after opening
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # Opening text printed.
        assert any(opening_text in m for m in ui.prints)
        # Opening text logged to session — read the flushed file because
        # _finalize() calls flush() which clears session.entries.
        session_files = list(
            (project_dir / ".anappt" / "session_history").iterdir()
        )
        assert len(session_files) == 1
        flushed = session_files[0].read_text(encoding="utf-8")
        assert opening_text in flushed
        # S1 transitioned to in_progress on entry.
        s1 = state.get_stage("S1")
        assert s1 is not None
        assert s1.status.value == "in_progress"

    def test_opening_calls_llm_with_system_prompt(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """The opening LLM call's messages list starts with a system prompt.

        S1 enables tools, so the opening turn goes through
        ``chat_with_tools`` (not ``chat``). The first such call carries
        the system prompt mentioning the current stage.
        """
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=[])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # First chat_with_tools call (opening). Inspect its messages.
        first_call_args = llm.chat_with_tools.call_args_list[0]
        _role, messages, _tools = first_call_args.args
        assert messages[0]["role"] == "system"
        # System prompt mentions the current stage.
        assert "S1" in messages[0]["content"]


# ---------------------------------------------------------------------------
# 2. Free-text turn
# ---------------------------------------------------------------------------


class TestFreeTextTurn:
    """User free text flows through the LLM; reply is printed + logged."""

    def test_user_text_and_llm_reply(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        # Opening (chat_with_tools call 1) + user reply (call 2).
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[
                {"content": "Opening prompt.", "tool_calls": []},
                {"content": "Reply to user question.", "tool_calls": []},
            ],
        )
        ui = FakeUI(inputs=["What should I do first?"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # Both opening and reply printed.
        assert any("Opening prompt." in m for m in ui.prints)
        assert any("Reply to user question." in m for m in ui.prints)
        # User input + agent reply both logged (read from flushed file).
        session_files = list(
            (project_dir / ".anappt" / "session_history").iterdir()
        )
        assert len(session_files) == 1
        flushed = session_files[0].read_text(encoding="utf-8")
        assert "What should I do first?" in flushed
        assert "Reply to user question." in flushed


# ---------------------------------------------------------------------------
# 3. Tool calling
# ---------------------------------------------------------------------------


class TestToolCalling:
    """chat_with_tools first returns a tool_call, then a final text."""

    def test_write_artifact_tool_writes_file(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        tool_call = {
            "id": "call_1",
            "name": "write_artifact",
            "arguments": (
                '{"rel_path": "report.yaml", "content": "project: {}"}'
            ),
        }
        # Opening: tool_call iteration + final text iteration.
        # Then the user types "ok" — a free-text turn that needs its
        # own chat_with_tools response.
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[
                {"content": "Writing report.yaml now.", "tool_calls": [tool_call]},
                {
                    "content": "Opening: report.yaml written. Please review.",
                    "tool_calls": [],
                },
                {"content": "Reply to ok.", "tool_calls": []},
            ],
        )
        ui = FakeUI(inputs=["ok"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # The file was actually written by the tool.
        written = project_dir / "report.yaml"
        assert written.exists()
        assert written.read_text(encoding="utf-8") == "project: {}"
        # The final opening text was printed.
        assert any(
            "Opening: report.yaml written. Please review." in m for m in ui.prints
        )

    def test_unknown_tool_returns_error_string(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """A tool name not in the active registry yields an error result,
        but the conversation loop continues to a final text."""
        bad_call = {
            "id": "call_1",
            "name": "render_deck",  # NOT enabled in S1
            "arguments": '{"goal_json_path": "x", "output_html_path": "y"}',
        }
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[
                {"content": "trying render", "tool_calls": [bad_call]},
                {"content": "render not available; anyway...", "tool_calls": []},
            ],
        )
        ui = FakeUI(inputs=[])  # exit immediately after opening
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # The error path was fed back; final text still printed.
        assert any(
            "render not available; anyway..." in m for m in ui.prints
        )
        # The tool message fed back to the LLM mentions the unknown tool.
        # Inspect the second chat_with_tools call's messages list.
        second_call_args = llm.chat_with_tools.call_args_list[1]
        _role, messages, _tools = second_call_args.args
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert tool_msgs
        assert "render_deck" in tool_msgs[0]["content"]

    def test_tool_argument_parse_error(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """Malformed JSON arguments yield an error string, loop continues."""
        bad_call = {
            "id": "call_1",
            "name": "read_file",
            "arguments": "not-valid-json{",
        }
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[
                {"content": "calling read_file", "tool_calls": [bad_call]},
                {"content": "recovered from bad args.", "tool_calls": []},
            ],
        )
        ui = FakeUI(inputs=[])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # Final text printed despite the bad-args error.
        assert any("recovered from bad args." in m for m in ui.prints)
        # The tool message fed back contains an error indicator.
        second_call_args = llm.chat_with_tools.call_args_list[1]
        _role, messages, _tools = second_call_args.args
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert tool_msgs
        assert "Error" in tool_msgs[0]["content"]


# ---------------------------------------------------------------------------
# 4. confirm advances the stage
# ---------------------------------------------------------------------------


class TestConfirmAdvance:
    """confirm triggers in_progress→completed and advances current_stage."""

    def _make_s1_ready(self, project_dir: Path) -> None:
        """Pre-create the S1 artifacts so is_ready() returns True."""
        (project_dir / "report.yaml").write_text(
            COMPLETE_REPORT_YAML, encoding="utf-8"
        )
        (project_dir / ".anappt" / "s1_topic.md").write_text(
            "# Topic\n\nDetailed topic doc.", encoding="utf-8"
        )

    def test_confirm_advances_and_commits(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        self._make_s1_ready(project_dir)
        # S1 opening + S2 opening (after advance).
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[
                {"content": "S1 opening.", "tool_calls": []},
                {"content": "S2 opening.", "tool_calls": []},
            ],
        )
        git = MagicMock()
        ui = FakeUI(inputs=["/confirm"])  # after S1 opening, user confirms
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui, git=git)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # S1 should be completed; current_stage should be S2.
        s1 = state.get_stage("S1")
        assert s1 is not None
        assert s1.status.value == "completed"
        assert state.state.current_stage == "S2"
        # commit_on_confirm invoked with S1 + its display name.
        git.commit_on_confirm.assert_called_once()
        args = git.commit_on_confirm.call_args.args
        assert args[0] == "S1"

    def test_confirm_after_advance_enters_next_stage_opening(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """After confirm, the runner produces an opening for the next stage."""
        self._make_s1_ready(project_dir)
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[
                {"content": "S1 opening.", "tool_calls": []},
                {"content": "S2 opening after advance.", "tool_calls": []},
            ],
        )
        ui = FakeUI(inputs=["/confirm"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # Both openings printed.
        assert any("S1 opening." in m for m in ui.prints)
        assert any("S2 opening after advance." in m for m in ui.prints)
        # Message history reset between stages.
        # After the S2 opening, the persisted messages list contains
        # the S2 instruction + S2 opening only.
        assert len(runner.messages) == 2
        assert runner.messages[0]["role"] == "user"
        assert runner.messages[1]["content"] == "S2 opening after advance."


# ---------------------------------------------------------------------------
# 5. confirm rejected when is_ready is False
# ---------------------------------------------------------------------------


class TestConfirmNotReady:
    """confirm with is_ready False does NOT advance the stage."""

    def test_confirm_not_ready_does_not_advance(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        # No artifacts created → S1 is_ready False.
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[{"content": "S1 opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/confirm"])  # rejected; then exit
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # S1 still in_progress; current_stage still S1.
        s1 = state.get_stage("S1")
        assert s1 is not None
        assert s1.status.value == "in_progress"
        assert state.state.current_stage == "S1"
        # not_ready message printed.
        assert any("尚未就绪" in m for m in ui.prints)


# ---------------------------------------------------------------------------
# 6. exit triggers finalization
# ---------------------------------------------------------------------------


class TestExitFinalize:
    """On exit, finalize_summary / flush / memory.update / commit_on_exit fire."""

    def test_exit_triggers_finalize_and_commit(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        llm = _make_llm(
            chat_return="Opening then summary text.",
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        git = MagicMock()
        ui = FakeUI(inputs=[])  # immediate exit
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui, git=git)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # session.finalize_summary calls llm.chat; the chat mock was
        # called at least once (for finalize_summary and memory.update).
        assert llm.chat.call_count >= 1
        # The session file was flushed (entries cleared + file written).
        files = list((project_dir / ".anappt" / "session_history").iterdir())
        assert len(files) == 1
        assert files[0].name.endswith("_S1.md")
        # memory.update invoked (best-effort). Since the LLM returns
        # non-NO_UPDATE text, the memory file is written.
        assert (project_dir / ".anappt" / "memory.md").exists()
        # git.commit_on_exit invoked.
        git.commit_on_exit.assert_called_once()

    def test_finalize_swallows_exceptions(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """A failure in finalize_summary should not abort the rest of _finalize."""
        # Opening goes through chat_with_tools (1 call).
        # finalize_summary → chat raises.
        # memory.update → chat returns "NO_UPDATE".
        llm = _make_llm(
            chat_side_effect=[
                RuntimeError("summary failed"),  # finalize_summary
                "NO_UPDATE",  # memory.update
            ],
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        git = MagicMock()
        ui = FakeUI(inputs=[])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui, git=git)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        # Must not raise.
        runner.run()

        # git.commit_on_exit still invoked despite the summary failure.
        git.commit_on_exit.assert_called_once()


# ---------------------------------------------------------------------------
# 7. Interactive-mode system prompt contains history index + artifacts listing
# ---------------------------------------------------------------------------


class TestInteractiveSystemPrompt:
    """In interactive mode, the system prompt contains the history index
    and the artifacts listing sections."""

    def test_interactive_prompt_contains_history_and_artifacts(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        # Pre-create a session-history file so the index is non-empty.
        (project_dir / ".anappt" / "session_history" / "2026-07-22_S1.md").write_text(
            "# prior session", encoding="utf-8"
        )
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[
                {"content": "Interactive opening.", "tool_calls": []},
            ],
        )
        ui = FakeUI(inputs=[])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="interactive", ui=ui)
        runner.run()

        # Inspect the system prompt of the first chat_with_tools call.
        first_call_args = llm.chat_with_tools.call_args_list[0]
        _role, messages, _tools = first_call_args.args
        sys_prompt = messages[0]["content"]
        assert "## 历史会话索引" in sys_prompt
        assert "## 当前产出物" in sys_prompt
        # The history index lists the prior file.
        assert "2026-07-22_S1.md" in sys_prompt
        # The artifacts listing mentions S1's declared artifacts.
        assert "report.yaml" in sys_prompt

    def test_run_mode_prompt_omits_history_section(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[{"content": "Run opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=[])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        first_call_args = llm.chat_with_tools.call_args_list[0]
        _role, messages, _tools = first_call_args.args
        sys_prompt = messages[0]["content"]
        # Run mode must NOT include the interactive-only sections.
        assert "## 历史会话索引" not in sys_prompt
        assert "## 当前产出物" not in sys_prompt
        # But it does include the run directive.
        assert "## 运行模式指令" in sys_prompt


# ---------------------------------------------------------------------------
# 8. read_history tool
# ---------------------------------------------------------------------------


class TestReadHistoryTool:
    """The read_history tool returns session_history file contents."""

    def test_read_history_returns_content(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        # Pre-create a session-history file.
        history_dir = project_dir / ".anappt" / "session_history"
        (history_dir / "2026-07-22_S4.md").write_text(
            "## 核心摘要\nPast S4 analysis.\n\n### 对话记录\n...",
            encoding="utf-8",
        )
        # Opening: 1 tool call (read_history S4) + final text.
        # Then a user turn "ok" → 1 more chat_with_tools response.
        tool_call = {
            "id": "call_1",
            "name": "read_history",
            "arguments": '{"target": "S4"}',
        }
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[
                {"content": "reading history", "tool_calls": [tool_call]},
                {"content": "S1 opening referencing past S4.", "tool_calls": []},
                {"content": "Reply to ok.", "tool_calls": []},
            ],
        )
        ui = FakeUI(inputs=["ok"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # The tool result fed back to the LLM contains the file content.
        second_call_args = llm.chat_with_tools.call_args_list[1]
        _role, messages, _tools = second_call_args.args
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert tool_msgs
        assert "Past S4 analysis." in tool_msgs[0]["content"]

    def test_read_history_target_all(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        history_dir = project_dir / ".anappt" / "session_history"
        (history_dir / "2026-07-21_S1.md").write_text("S1 day 1", encoding="utf-8")
        (history_dir / "2026-07-22_S4.md").write_text("S4 day 2", encoding="utf-8")

        tool_call = {
            "id": "call_1",
            "name": "read_history",
            "arguments": '{"target": "all"}',
        }
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[
                {"content": "reading", "tool_calls": [tool_call]},
                {"content": "done", "tool_calls": []},
            ],
        )
        ui = FakeUI(inputs=[])  # exit after opening
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        second_call_args = llm.chat_with_tools.call_args_list[1]
        _role, messages, _tools = second_call_args.args
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert tool_msgs
        # Both files' content appears.
        assert "S1 day 1" in tool_msgs[0]["content"]
        assert "S4 day 2" in tool_msgs[0]["content"]


# ---------------------------------------------------------------------------
# Misc: meta-commands status / memory / help
# ---------------------------------------------------------------------------


class TestMetaCommands:
    """status / memory / help meta-commands behave as expected."""

    def test_status_meta_calls_ui_table(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/status"])  # then exit
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # status renders a table with 6 stages.
        assert len(ui.tables) == 1
        headers, rows = ui.tables[0]
        assert "ID" in headers
        assert len(rows) == 6  # S1..S6

    def test_memory_meta_prints_memory(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        # Write a memory file with content.
        memory_file = project_dir / ".anappt" / "memory.md"
        memory_file.write_text("# Memory\n- audience confirmed", encoding="utf-8")

        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/memory"])  # then exit
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # Memory content printed.
        assert any("audience confirmed" in m for m in ui.prints)

    def test_help_meta_prints_help_text(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/help"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # Help text mentions confirm.
        assert any("confirm" in m for m in ui.prints)


# ---------------------------------------------------------------------------
# Misc: EOF handling
# ---------------------------------------------------------------------------


class TestEOFHandling:
    """When ui.input returns None (EOF), the runner exits cleanly."""

    def test_eof_exits_cleanly(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )

        class EOFUI(FakeUI):
            def input(self, prompt: str) -> str | None:
                return None

        ui = EOFUI()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        # Must not raise.
        runner.run()

        # Opening was still printed.
        assert any("Opening." in m for m in ui.prints)


# ---------------------------------------------------------------------------
# Misc: empty input is skipped
# ---------------------------------------------------------------------------


class TestEmptyInputSkipped:
    """Empty/whitespace-only input is skipped (not sent to LLM)."""

    def test_empty_input_does_not_call_llm_again(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["", "   "])  # then exit
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # Only the opening LLM call (no extra chat_with_tools for empty
        # inputs). chat_with_tools is called exactly once.
        assert llm.chat_with_tools.call_count == 1
        # The persisted messages list contains only the opening pair
        # (no user free-text turn was appended).
        assert len(runner.messages) == 2  # instruction + opening reply


# ---------------------------------------------------------------------------
# 9. update_memory tool (callable + ToolDef)
# ---------------------------------------------------------------------------


class TestUpdateMemoryTool:
    """The update_memory tool appends to memory.md and reports OK."""

    def test_update_memory_appends_and_returns_ok(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        llm = _make_llm()
        ui = FakeUI()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)

        funcs = runner._build_tool_funcs()
        assert "update_memory" in funcs
        result = funcs["update_memory"](content="关键发现:渠道 A ROI 最高")

        # Return string signals success and reports char count.
        assert result.startswith("OK:")
        assert str(len("关键发现:渠道 A ROI 最高")) in result
        # The entry was actually appended to memory.md.
        assert "关键发现:渠道 A ROI 最高" in memory.read()

    def test_update_memory_without_memory_manager_returns_error(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
    ) -> None:
        """When ctx.memory is None, the closure returns an error string."""
        llm = _make_llm()
        ui = FakeUI()
        # Build ctx without a memory manager.
        ctx = PipelineContext(
            project_dir=project_dir,
            config=ReportConfig(),
            llm=llm,
            state=state,
            ui=ui,
            session=session,
            git=None,
            memory=None,
        )
        runner = ConversationRunner(ctx, mode="run", ui=ui)

        funcs = runner._build_tool_funcs()
        result = funcs["update_memory"](content="anything")

        assert result == "Error: memory manager not available"

    def test_update_memory_tool_def_requires_content(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """The update_memory ToolDef marks ``content`` as required."""
        llm = _make_llm()
        ui = FakeUI()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)

        defs = runner._build_tool_defs()
        assert "update_memory" in defs
        params = defs["update_memory"].parameters
        assert "content" in params["required"]


# ---------------------------------------------------------------------------
# 10. _finalize ordering regression (session_content captured before flush)
# ---------------------------------------------------------------------------


class TestFinalizeOrdering:
    """Regression: ``memory.update`` receives the full session text even though
    ``flush()`` clears the in-memory entries buffer.

    The bug being guarded against: ``_finalize`` used to call
    ``session.get_full_text()`` *after* ``flush()``, by which point the
    buffer was empty — so ``memory.update`` got an empty session_content.
    The fix caches ``session_full_text`` before ``flush()``.
    """

    def test_memory_update_receives_non_empty_session_content(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        # A unique marker logged into the session entries. If the
        # session_content passed to memory.update is non-empty, this
        # marker must appear in the memory.update user prompt.
        marker = "UNIQUE_MARKER_42_渠道ROI峰值出现在七月"

        # Populate the session buffer with real entries.
        session.new_session("S1")
        session.log_user("用户问了一个问题")
        session.log_agent(marker)

        # LLM returns NO_UPDATE so memory.update writes nothing (we only
        # care about the prompt it received). Both finalize_summary and
        # memory.update go through llm.chat.
        llm = _make_llm(chat_return="NO_UPDATE")
        ui = FakeUI()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)

        runner._finalize()

        # llm.chat was called at least twice (finalize_summary + memory.update).
        assert llm.chat.call_count >= 2

        # Find the memory.update call: its user prompt contains both
        # memory-section and session-section headers (see MemoryManager.update).
        memory_calls = []
        for call in llm.chat.call_args_list:
            _role, messages = call.args
            user_content = messages[-1]["content"]
            if (
                "=== 当前 memory.md ===" in user_content
                and "=== 本次会话内容 ===" in user_content
            ):
                memory_calls.append(user_content)
        assert len(memory_calls) == 1, "expected exactly one memory.update call"

        # The session_content passed to memory.update still carries the
        # marker logged before flush — proving get_full_text ran first.
        assert marker in memory_calls[0]

        # flush() still executed: an archived session file was written.
        session_files = list(
            (project_dir / ".anappt" / "session_history").iterdir()
        )
        assert len(session_files) >= 1
        assert any(f.name.endswith("_S1.md") for f in session_files)


# ---------------------------------------------------------------------------
# 11. ``/``-prefixed meta-commands (Task 5 / SubTask 5.4)
# ---------------------------------------------------------------------------


class TestSlashMetaCommands:
    """``/``-prefixed meta-commands and free-text fall-through.

    Verifies that:
      - ``/confirm``, ``/exit``, ``/Status`` (case-insensitive) trigger
        the corresponding logic.
      - ``/foo``, bare ``confirm``, bare ``退出``, bare ``help`` are NOT
        recognized as meta-commands — they fall through to the LLM as
        free text (``_handle_meta`` returns ``False``).
    """

    def test_slash_confirm_triggers_confirm(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        # S1 is_ready is False (no artifacts) → confirm prints not_ready.
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/confirm"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # confirm was dispatched: not_ready printed; S1 still in_progress.
        assert any("尚未就绪" in m for m in ui.prints)
        assert state.get_stage("S1").status.value == "in_progress"
        # No second LLM turn happened (only the opening).
        assert llm.chat_with_tools.call_count == 1

    def test_slash_confirm_direct_handle_meta_returns_true(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """``_handle_meta("/confirm")`` returns True without LLM call."""
        llm = _make_llm()
        ui = FakeUI()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)

        assert runner._handle_meta("/confirm") is True
        # LLM was NOT called by _handle_meta.
        assert llm.chat_with_tools.call_count == 0
        assert llm.chat.call_count == 0

    def test_slash_exit_sets_exit_flag(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        llm = _make_llm(
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/exit"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        assert runner._exit is True
        # Only the opening LLM call happened; /exit did not call LLM.
        assert llm.chat_with_tools.call_count == 1

    def test_slash_status_case_insensitive(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        llm = _make_llm(
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/Status"])  # case-insensitive
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # /Status triggered _show_status → table rendered with 6 stages.
        assert len(ui.tables) == 1
        _headers, rows = ui.tables[0]
        assert len(rows) == 6

    def test_slash_memory_case_insensitive(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        # Pre-write memory content.
        (project_dir / ".anappt" / "memory.md").write_text(
            "# Memory\n- audience confirmed", encoding="utf-8"
        )
        llm = _make_llm(
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/MEMORY"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        assert any("audience confirmed" in m for m in ui.prints)

    def test_slash_help_dispatches(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        llm = _make_llm(
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/help"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # Help text printed (mentions /confirm).
        assert any("/confirm" in m for m in ui.prints)

    def test_slash_unknown_returns_false(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """/foo is not a recognized meta-command → returns False."""
        llm = _make_llm()
        ui = FakeUI()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)

        assert runner._handle_meta("/foo") is False
        assert runner._handle_meta("/foo bar baz") is False

    def test_slash_unknown_falls_through_to_llm(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """/foo bar is treated as free text → sent to the LLM."""
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[
                {"content": "Opening.", "tool_calls": []},
                {"content": "Reply to /foo bar.", "tool_calls": []},
            ],
        )
        ui = FakeUI(inputs=["/foo bar"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # The second chat_with_tools call carried "/foo bar" as the
        # latest user message.
        second_call_args = llm.chat_with_tools.call_args_list[1]
        _role, messages, _tools = second_call_args.args
        user_msgs = [m for m in messages if m.get("role") == "user"]
        assert user_msgs
        assert user_msgs[-1]["content"] == "/foo bar"
        # Reply printed.
        assert any("Reply to /foo bar." in m for m in ui.prints)

    def test_bare_confirm_returns_false(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """Bare 'confirm' (no /) is free text, not a meta-command."""
        llm = _make_llm()
        ui = FakeUI()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)

        assert runner._handle_meta("confirm") is False

    def test_bare_chinese_aliases_return_false(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """Bare Chinese aliases ('退出', '帮助') and 'quit' are free text."""
        llm = _make_llm()
        ui = FakeUI()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)

        for text in ("退出", "帮助", "quit", "exit", "status", "memory", "help"):
            assert runner._handle_meta(text) is False, (
                f"{text!r} should NOT be a meta-command"
            )

    def test_bare_confirm_falls_through_to_llm(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """Bare 'confirm' is sent to the LLM as free text."""
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[
                {"content": "Opening.", "tool_calls": []},
                {"content": "I see you typed confirm.", "tool_calls": []},
            ],
        )
        ui = FakeUI(inputs=["confirm"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner.run()

        # The second chat_with_tools call carried "confirm" as the
        # latest user message (not treated as a meta-command).
        second_call_args = llm.chat_with_tools.call_args_list[1]
        _role, messages, _tools = second_call_args.args
        user_msgs = [m for m in messages if m.get("role") == "user"]
        assert user_msgs[-1]["content"] == "confirm"
        # Reply printed.
        assert any("I see you typed confirm." in m for m in ui.prints)


# ---------------------------------------------------------------------------
# 12. StreamingSink integration (Task 4 / SubTask 4.5)
# ---------------------------------------------------------------------------


class FakeSink:
    """Recording StreamingSink for unit tests.

    Records every call so tests can assert on the exact sequence of
    ``user_message`` / ``assistant_message`` / ``thinking_update`` /
    ``thinking_idle`` / ``thinking_clear`` invocations.
    """

    def __init__(self) -> None:
        self.user_messages: list[str] = []
        self.assistant_messages: list[str] = []
        self.thinking_updates: list[str] = []
        self.thinking_idles: list[str] = []
        self.thinking_clears: int = 0

    def user_message(self, text: str) -> None:
        self.user_messages.append(text)

    def assistant_message(self, text: str) -> None:
        self.assistant_messages.append(text)

    def thinking_update(self, buf: str) -> None:
        self.thinking_updates.append(buf)

    def thinking_idle(self, msg: str) -> None:
        self.thinking_idles.append(msg)

    def thinking_clear(self) -> None:
        self.thinking_clears += 1


class TestStreamingSinkIntegration:
    """Verify the streaming path drives the sink correctly.

    When ``stream_sink`` is injected, the runner uses
    ``chat_with_tools_stream`` (or ``chat_stream`` without tools) and
    pushes ``thinking_idle`` → ``thinking_update`` (per delta) →
    ``thinking_clear`` → ``assistant_message`` to the sink. The plain
    ``chat`` / ``chat_with_tools`` non-streaming methods are NOT
    called.
    """

    def test_stream_no_tools_chat_stream_used(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """With sink + no tools: chat_stream is used; sink receives
        thinking updates + final assistant_message."""
        # Build an LLM mock whose chat_stream yields content deltas.
        llm = MagicMock()
        llm.chat_stream.return_value = iter(["Hel", "lo", " world"])
        # _finalize calls chat (best-effort) — give it a harmless return.
        llm.chat.return_value = "NO_UPDATE"

        ui = FakeUI(inputs=[])  # immediate exit after opening
        sink = FakeSink()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)

        # Force a stage with no tools: patch _tool_schemas to return [].
        runner = ConversationRunner(ctx, mode="run", ui=ui, stream_sink=sink)
        runner._tool_schemas = lambda: []  # type: ignore[method-assign]
        runner.run()

        # chat_stream was used (not chat_with_tools / chat for the turn).
        llm.chat_stream.assert_called_once()
        llm.chat_with_tools_stream.assert_not_called()
        llm.chat_with_tools.assert_not_called()
        # thinking_idle called once before the stream; thinking_clear once
        # after; thinking_update called once per delta (3 deltas).
        assert len(sink.thinking_idles) == 1
        assert sink.thinking_clears == 1
        assert len(sink.thinking_updates) == 3
        # thinking_updates carry the accumulated buffer at each step.
        assert sink.thinking_updates[0] == "Hel"
        assert sink.thinking_updates[1] == "Hello"
        assert sink.thinking_updates[2] == "Hello world"
        # assistant_message received the full text.
        assert sink.assistant_messages == ["Hello world"]
        # No ui.print for the assistant text (sink handled it).
        assert all("Hello world" not in m for m in ui.prints)

    def test_stream_with_tools_content_only(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """With sink + tools: chat_with_tools_stream yields content
        events only (no tool_calls); assistant_message receives the
        full content."""
        llm = MagicMock()
        # Single round: content deltas, no tool_calls.
        llm.chat_with_tools_stream.return_value = iter([
            {"type": "content", "delta": "Hello"},
            {"type": "content", "delta": " world"},
        ])
        llm.chat.return_value = "NO_UPDATE"  # for _finalize

        ui = FakeUI(inputs=[])
        sink = FakeSink()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui, stream_sink=sink)
        runner.run()

        # Streaming path used.
        llm.chat_with_tools_stream.assert_called_once()
        llm.chat_with_tools.assert_not_called()
        llm.chat_stream.assert_not_called()
        # One idle + one clear + 2 updates (one per content delta).
        assert len(sink.thinking_idles) == 1
        assert sink.thinking_clears == 1
        assert len(sink.thinking_updates) == 2
        assert sink.thinking_updates[0] == "Hello"
        assert sink.thinking_updates[1] == "Hello world"
        # Final assistant message has the full content.
        assert sink.assistant_messages == ["Hello world"]

    def test_stream_with_tools_tool_call_then_content(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """With sink + tools: first round emits a tool_call (name +
        arguments split across chunks); tool is executed; second round
        emits final content. Verifies tool execution + final text."""
        # The tool to call: write_artifact with rel_path + content.
        wa_args_partial1 = '{"rel_path": '
        wa_args_partial2 = '"hello.txt", "content": "hi"}'
        # Round 1 events: tool_call (id+name) → tool_call (args1) →
        # tool_call (args2). Round 2 events: content deltas.
        def stream_side_effect(role, messages, tools):
            # Inspect the latest message to decide which round we are in.
            # Round 1: messages = [system, user_instruction]
            # Round 2: messages = [system, user_instruction, assistant
            #           (with tool_calls), tool (result)]
            if any(m.get("role") == "tool" for m in messages):
                # Round 2: yield content.
                yield {"type": "content", "delta": "Wrote "}
                yield {"type": "content", "delta": "the file."}
                return
            # Round 1: yield tool_call fragments.
            yield {
                "type": "tool_call",
                "tool_call": {
                    "index": 0,
                    "id": "call_1",
                    "name": "write_artifact",
                    "arguments": None,
                },
            }
            yield {
                "type": "tool_call",
                "tool_call": {
                    "index": 0,
                    "id": None,
                    "name": None,
                    "arguments": wa_args_partial1,
                },
            }
            yield {
                "type": "tool_call",
                "tool_call": {
                    "index": 0,
                    "id": None,
                    "name": None,
                    "arguments": wa_args_partial2,
                },
            }

        llm = MagicMock()
        llm.chat_with_tools_stream.side_effect = stream_side_effect
        llm.chat.return_value = "NO_UPDATE"

        ui = FakeUI(inputs=[])
        sink = FakeSink()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui, stream_sink=sink)
        runner.run()

        # Two streaming rounds happened (tool_call + final content).
        assert llm.chat_with_tools_stream.call_count == 2
        # Two idle + two clear (one per round).
        assert len(sink.thinking_idles) == 2
        assert sink.thinking_clears == 2
        # The tool was actually executed: hello.txt was written.
        written = project_dir / "hello.txt"
        assert written.exists()
        assert written.read_text(encoding="utf-8") == "hi"
        # Final assistant_message has the round-2 content.
        assert sink.assistant_messages == ["Wrote the file."]
        # No plain chat_with_tools / chat_stream calls for the turn.
        llm.chat_with_tools.assert_not_called()
        llm.chat_stream.assert_not_called()

    def test_stream_user_message_echoed(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """With sink, user input is echoed via sink.user_message before
        the LLM turn."""
        llm = MagicMock()
        # Opening: 1 round content; user turn: 1 round content.
        llm.chat_with_tools_stream.side_effect = [
            iter([{"type": "content", "delta": "Opening."}]),
            iter([{"type": "content", "delta": "Reply."}]),
        ]
        llm.chat.return_value = "NO_UPDATE"

        ui = FakeUI(inputs=["hi there"])
        sink = FakeSink()
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui, stream_sink=sink)
        runner.run()

        # The user's "hi there" was echoed via sink.user_message.
        assert "hi there" in sink.user_messages
        # Both opening and reply rendered via sink.assistant_message.
        assert sink.assistant_messages == ["Opening.", "Reply."]

    def test_no_sink_uses_nonstream_path(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """Without sink, the runner uses chat_with_tools (non-stream)."""
        llm = _make_llm(
            chat_return="finalize",
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=[])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)  # no sink
        runner.run()

        # Non-streaming path used.
        llm.chat_with_tools.assert_called_once()
        llm.chat_with_tools_stream.assert_not_called()
        llm.chat_stream.assert_not_called()


# ---------------------------------------------------------------------------
# 13. ``/ppt <requirement>`` direct generation (Task 6 / SubTask 6.5)
# ---------------------------------------------------------------------------


class TestPptDirect:
    """Tests for the ``/ppt <requirement>`` direct-generation command.

    Covers:
      - skill missing → ``conv.ppt_skill_missing`` printed, no LLM call.
      - skill present (mocked) → LLM is called with S6 tools; goal.json
        written; render_deck triggered; stage state + self.messages
        unchanged.
      - ``/ppt`` (empty requirement) → ``conv.ppt_empty_requirement``.
    """

    def test_ppt_skill_missing_prints_notice_no_llm_call(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """When _get_skill_root returns None, /ppt prints the
        skill-missing notice and does NOT invoke the LLM."""
        llm = _make_llm(
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/ppt 生成关于 Q3 的 PPT"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        # Force _get_skill_root to return None (skill not installed).
        runner._get_skill_root = lambda: None  # type: ignore[method-assign]
        runner.run()

        # Skill-missing notice printed (contains the key substring).
        assert any("dashi-ppt-skill 未安装" in m for m in ui.prints)
        # No LLM call beyond the opening (the /ppt branch returned early).
        # Only the opening used chat_with_tools; /ppt itself did NOT
        # invoke the LLM. (llm.chat is still called by _finalize for
        # finalize_summary + memory.update — that's expected and not
        # attributable to /ppt.)
        assert llm.chat_with_tools.call_count == 1
        # Pipeline state untouched.
        assert state.state.current_stage == "S1"

    def test_ppt_empty_requirement_prints_usage(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
    ) -> None:
        """/ppt with no requirement after the command prints usage."""
        llm = _make_llm(
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/ppt"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner._get_skill_root = lambda: None  # type: ignore[method-assign]
        runner.run()

        # Empty-requirement notice printed (i18n key text).
        assert any("请提供 PPT 生成需求" in m for m in ui.prints)
        # /ppt did not call the LLM (only the opening used chat_with_tools;
        # llm.chat calls come from _finalize, not /ppt).
        assert llm.chat_with_tools.call_count == 1

    def test_ppt_skill_present_runs_llm_with_s6_tools(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
        tmp_path: Path,
    ) -> None:
        """With skill present, /ppt loads SKILL.md, runs one LLM turn
        with the S6 tool subset, writes goal.json, triggers
        render_deck, and leaves state.yaml + self.messages unchanged.

        chat_with_tools call order:
          1. S1 opening (no tool_calls) — from ``_opening()``.
          2. /ppt tool_calls round (write_artifact + render_deck).
          3. /ppt final content round (no tool_calls).
        Then the FakeUI fallback ``/exit`` ends the loop.
        """
        # Build a fake skill root with a SKILL.md.
        skill_root = tmp_path / "dashi-ppt"
        skill_root.mkdir()
        (skill_root / "SKILL.md").write_text(
            "# Dashi PPT Skill\n\nSkill instructions.", encoding="utf-8"
        )

        goal_json_content = json.dumps(
            {
                "title": "Test",
                "goal": "Test goal",
                "audience": ["x"],
                "owner": "u",
                "randomSeed": 1,
                "pageCount": 5,
                "themePack": "theme01",
                "slides": [],
            },
            ensure_ascii=False,
        )
        wa_goal = {
            "id": "c1",
            "name": "write_artifact",
            "arguments": json.dumps(
                {"rel_path": "output/ppt/goal.json", "content": goal_json_content}
            ),
        }
        rd_call = {
            "id": "c2",
            "name": "render_deck",
            "arguments": json.dumps(
                {
                    "goal_json_path": "output/ppt/goal.json",
                    "output_html_path": "output/ppt/presentation.html",
                }
            ),
        }
        llm = MagicMock()
        # Order: S1 opening → /ppt tools round → /ppt final content.
        llm.chat_with_tools.side_effect = [
            {"content": "S1 opening.", "tool_calls": []},
            {"content": "Constructing goal.json.", "tool_calls": [wa_goal, rd_call]},
            {"content": "PPT rendered. Please review in browser.", "tool_calls": []},
        ]
        # _finalize calls chat (best-effort).
        llm.chat.return_value = "NO_UPDATE"

        ui = FakeUI(inputs=["/ppt 生成关于 Q3 的 PPT"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        # Force _get_skill_root to return our fake skill root.
        runner._get_skill_root = lambda: skill_root  # type: ignore[method-assign]

        # Patch DashiPPTBridge.render_deck to avoid subprocess; write a
        # fake presentation.html instead.
        def fake_render_deck(goal_json_path, output_html_path, skill_root):
            output_html_path = Path(output_html_path)
            output_html_path.parent.mkdir(parents=True, exist_ok=True)
            output_html_path.write_text(
                "<!DOCTYPE html><html><body>Mock</body></html>",
                encoding="utf-8",
            )
            return output_html_path

        with patch(
            "anappt.bridge.dashi_ppt.DashiPPTBridge.render_deck",
            side_effect=fake_render_deck,
        ):
            runner.run()

        # goal.json was written by the write_artifact tool.
        goal_json = project_dir / "output" / "ppt" / "goal.json"
        assert goal_json.exists()
        parsed = json.loads(goal_json.read_text(encoding="utf-8"))
        assert parsed["title"] == "Test"
        # presentation.html was written by render_deck.
        html = project_dir / "output" / "ppt" / "presentation.html"
        assert html.exists()
        # Final LLM reply + ppt_done notice printed.
        assert any("PPT rendered. Please review in browser." in m for m in ui.prints)
        assert any("浏览器" in m for m in ui.prints)  # conv.ppt_done

        # Pipeline state untouched (still S1 in_progress, never advanced).
        assert state.state.current_stage == "S1"
        assert state.get_stage("S1").status.value == "in_progress"
        # 3 chat_with_tools calls total: S1 opening + /ppt tools + /ppt final.
        assert llm.chat_with_tools.call_count == 3
        # The /ppt turn's first call (2nd overall) used S6 tools.
        ppt_call_args = llm.chat_with_tools.call_args_list[1]
        _role, ppt_messages, tools = ppt_call_args.args
        tool_names = {t["function"]["name"] for t in tools}
        assert "render_deck" in tool_names
        assert "write_artifact" in tool_names
        assert "export_pptx" in tool_names
        # The /ppt turn's system prompt contains the SKILL.md content.
        assert "Dashi PPT Skill" in ppt_messages[0]["content"]
        # The user message is the requirement.
        assert ppt_messages[1]["content"] == "生成关于 Q3 的 PPT"
        # Tools were restored after /ppt (S1 opening's tool list does
        # NOT contain render_deck).
        s1_call_args = llm.chat_with_tools.call_args_list[0]
        _r, _m, s1_tools = s1_call_args.args
        s1_names = {t["function"]["name"] for t in s1_tools}
        assert "render_deck" not in s1_names  # S1 doesn't have render_deck

    def test_ppt_skill_present_state_and_messages_unchanged(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
        tmp_path: Path,
    ) -> None:
        """``/ppt`` does not change state.yaml stage status or
        ``self.messages`` (the /ppt turn is independent)."""
        # Set up fake skill root.
        skill_root = tmp_path / "dashi-ppt"
        skill_root.mkdir()
        (skill_root / "SKILL.md").write_text("# Skill", encoding="utf-8")

        goal_json_content = json.dumps(
            {"title": "T", "goal": "G", "slides": []}, ensure_ascii=False
        )
        wa_goal = {
            "id": "c1",
            "name": "write_artifact",
            "arguments": json.dumps(
                {"rel_path": "output/ppt/goal.json", "content": goal_json_content}
            ),
        }
        rd_call = {
            "id": "c2",
            "name": "render_deck",
            "arguments": json.dumps(
                {
                    "goal_json_path": "output/ppt/goal.json",
                    "output_html_path": "output/ppt/presentation.html",
                }
            ),
        }
        llm = MagicMock()
        # Order: S1 opening (1 call), /ppt turn (2 calls: tools + final).
        llm.chat_with_tools.side_effect = [
            {"content": "S1 opening.", "tool_calls": []},
            {"content": "Constructing.", "tool_calls": [wa_goal, rd_call]},
            {"content": "PPT rendered.", "tool_calls": []},
        ]
        llm.chat.return_value = "NO_UPDATE"

        ui = FakeUI(inputs=["/ppt 生成 PPT"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner._get_skill_root = lambda: skill_root  # type: ignore[method-assign]

        def fake_render_deck(goal_json_path, output_html_path, skill_root):
            output_html_path = Path(output_html_path)
            output_html_path.parent.mkdir(parents=True, exist_ok=True)
            output_html_path.write_text("<html></html>", encoding="utf-8")
            return output_html_path

        with patch(
            "anappt.bridge.dashi_ppt.DashiPPTBridge.render_deck",
            side_effect=fake_render_deck,
        ):
            runner.run()

        # State unchanged.
        assert state.state.current_stage == "S1"
        assert state.get_stage("S1").status.value == "in_progress"
        # self.messages contains only the S1 opening pair (instruction +
        # opening reply). The /ppt turn was NOT appended.
        assert len(runner.messages) == 2
        assert runner.messages[0]["role"] == "user"  # opening instruction
        assert runner.messages[1]["content"] == "S1 opening."
        # goal.json + presentation.html exist.
        assert (project_dir / "output" / "ppt" / "goal.json").exists()
        assert (project_dir / "output" / "ppt" / "presentation.html").exists()
        # 3 chat_with_tools calls total: S1 opening + /ppt tools + /ppt final.
        assert llm.chat_with_tools.call_count == 3
        # The /ppt turn's first call used S6 tools (render_deck +
        # write_artifact + read_file + export_pptx + ...).
        ppt_call_args = llm.chat_with_tools.call_args_list[1]
        _role, _messages, tools = ppt_call_args.args
        tool_names = {t["function"]["name"] for t in tools}
        assert "render_deck" in tool_names
        assert "write_artifact" in tool_names
        assert "export_pptx" in tool_names
        # The /ppt turn's system prompt contains the SKILL.md content.
        ppt_messages = _messages
        assert "Skill" in ppt_messages[0]["content"]  # SKILL.md text
        # The user message is the requirement.
        assert ppt_messages[1]["content"] == "生成 PPT"
        # Tools were restored after /ppt (S1 tools back in place for
        # subsequent turns — verified by inspecting the S1 opening's
        # tool list, which should NOT contain render_deck).
        s1_call_args = llm.chat_with_tools.call_args_list[0]
        _r, _m, s1_tools = s1_call_args.args
        s1_names = {t["function"]["name"] for t in s1_tools}
        assert "render_deck" not in s1_names  # S1 doesn't have render_deck

    def test_ppt_load_skill_md_failure_prints_error(
        self,
        project_dir: Path,
        state: StateManager,
        session: SessionLogger,
        memory: MemoryManager,
        tmp_path: Path,
    ) -> None:
        """If load_skill_md raises, the error is printed and /ppt
        returns without calling the LLM."""
        skill_root = tmp_path / "dashi-ppt"
        skill_root.mkdir()
        # NOTE: no SKILL.md → load_skill_md raises FileNotFoundError.

        llm = _make_llm(
            chat_with_tools_responses=[{"content": "Opening.", "tool_calls": []}],
        )
        ui = FakeUI(inputs=["/ppt 生成 PPT"])
        ctx = _build_ctx(project_dir, state, session, memory, llm, ui)
        runner = ConversationRunner(ctx, mode="run", ui=ui)
        runner._get_skill_root = lambda: skill_root  # type: ignore[method-assign]
        runner.run()

        # Error message printed (mentions SKILL.md missing).
        assert any("SKILL.md" in m for m in ui.prints)
        # No LLM call beyond the S1 opening.
        assert llm.chat_with_tools.call_count == 1
