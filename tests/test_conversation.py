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

The tests use a FakeUI that returns canned input from a queue, plus
MagicMock LLMs with configurable chat / chat_with_tools return values.

Note on LLM call routing: S1 (and most stages) declare a non-empty
``tools(ctx)`` subset, so a turn's first LLM call goes through
``chat_with_tools`` (not ``chat``). The plain ``chat`` method is only
used by ``finalize_summary`` and ``memory.update`` during ``_finalize``,
and as a fallback when no tools are enabled.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

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
    queue is empty it returns ``"exit"`` to avoid infinite loops.

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
        return "exit"

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
        ui = FakeUI(inputs=["confirm"])  # after S1 opening, user confirms
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
        ui = FakeUI(inputs=["confirm"])
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
        ui = FakeUI(inputs=["confirm"])  # rejected; then exit
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
        ui = FakeUI(inputs=["status"])  # then exit
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
        ui = FakeUI(inputs=["memory"])  # then exit
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
        ui = FakeUI(inputs=["help"])
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
