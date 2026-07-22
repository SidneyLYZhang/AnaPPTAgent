"""Tests for SessionLogger and read_history (Task D1 + D3)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt import i18n
from anappt.io.session import SessionLogger, read_history


@pytest.fixture(autouse=True)
def force_zh_locale():
    """Force the zh locale so spec-described Chinese strings are used.

    The spec describes flush output with Chinese headers (``## 核心摘要``,
    ``未生成摘要``, ``### 对话记录``). The test environment may otherwise
    detect ``en`` from ``LANG``/``LANGUAGE``, which would render English
    headers and break string assertions. Each test is reset and restored
    to keep locale state isolated.
    """
    i18n._reset_cache()
    i18n.set_locale("zh")
    yield
    i18n._reset_cache()


def _today_utc() -> str:
    """Return today's UTC date in YYYY-MM-DD form (matches SessionLogger naming)."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    """Create a session directory."""
    d = tmp_path / ".anappt" / "session_history"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def logger(session_dir: Path) -> SessionLogger:
    """Return a SessionLogger instance."""
    return SessionLogger(session_dir)


@pytest.fixture
def mock_llm() -> MagicMock:
    """Return a mock AnaPPTLLM with a canned chat response."""
    mock = MagicMock()
    mock.chat.return_value = "Mock summary of the conversation."
    return mock


class TestSessionLoggerInit:
    """Tests for SessionLogger initialization."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "new_session_dir"
        SessionLogger(session_dir)
        assert session_dir.exists()
        assert session_dir.is_dir()

    def test_creates_nested_directory(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "a" / "b" / "c"
        SessionLogger(session_dir)
        assert session_dir.exists()

    def test_initial_state(self, session_dir: Path) -> None:
        logger = SessionLogger(session_dir)
        assert logger.current_stage == ""
        assert logger.entries == []
        assert logger._pending_summary is None


class TestNewSession:
    """Tests for new_session method."""

    def test_sets_current_stage(self, logger: SessionLogger) -> None:
        logger.new_session("S1")
        assert logger.current_stage == "S1"

    def test_clears_entries(self, logger: SessionLogger) -> None:
        logger.log_agent("some content")
        logger.new_session("S2")
        # new_session adds a system entry, but old entries are cleared
        roles = [e[0] for e in logger.entries]
        assert "agent" not in roles  # old agent entry cleared

    def test_adds_system_entry(self, logger: SessionLogger) -> None:
        logger.new_session("S1")
        assert len(logger.entries) == 1
        assert logger.entries[0][0] == "system"

    def test_flushes_previous(self, logger: SessionLogger, session_dir: Path) -> None:
        logger.new_session("S1")
        logger.log_agent("content for S1")
        logger.new_session("S2")
        # S1 session file should exist with the new date-based naming.
        s1_file = session_dir / f"{_today_utc()}_S1.md"
        assert s1_file.exists()


class TestLogAgent:
    """Tests for log_agent method."""

    def test_adds_entry(self, logger: SessionLogger) -> None:
        logger.log_agent("Hello from agent")
        assert len(logger.entries) == 1
        role, timestamp, content = logger.entries[0]
        assert role == "agent"
        assert content == "Hello from agent"
        assert timestamp  # non-empty

    def test_multiple_entries(self, logger: SessionLogger) -> None:
        logger.log_agent("First message")
        logger.log_agent("Second message")
        assert len(logger.entries) == 2
        assert logger.entries[0][2] == "First message"
        assert logger.entries[1][2] == "Second message"

    def test_timestamp_format(self, logger: SessionLogger) -> None:
        logger.log_agent("test")
        _, timestamp, _ = logger.entries[0]
        # ISO format should contain 'T'
        assert "T" in timestamp


class TestLogUser:
    """Tests for log_user method."""

    def test_adds_entry(self, logger: SessionLogger) -> None:
        logger.log_user("User input")
        assert len(logger.entries) == 1
        role, timestamp, content = logger.entries[0]
        assert role == "user"
        assert content == "User input"

    def test_multiple_entries(self, logger: SessionLogger) -> None:
        logger.log_user("First")
        logger.log_user("Second")
        assert len(logger.entries) == 2

    def test_mixed_entries(self, logger: SessionLogger) -> None:
        logger.log_agent("Agent says hi")
        logger.log_user("User responds")
        assert len(logger.entries) == 2
        assert logger.entries[0][0] == "agent"
        assert logger.entries[1][0] == "user"


class TestFlush:
    """Tests for flush method (Task D1: YYYY-MM-DD_<stage>.md, append)."""

    def test_writes_file_with_date_naming(
        self, logger: SessionLogger, session_dir: Path
    ) -> None:
        logger.new_session("S1")
        logger.log_agent("Test content")
        result = logger.flush()
        assert result is not None
        assert result.exists()
        # New naming: YYYY-MM-DD_S1.md (UTC date).
        expected = session_dir / f"{_today_utc()}_S1.md"
        assert result == expected

    def test_file_content_has_agent_header(self, logger: SessionLogger) -> None:
        logger.new_session("S1")
        logger.log_agent("Agent message")
        filepath = logger.flush()
        assert filepath is not None
        content = filepath.read_text(encoding="utf-8")
        assert "Agent message" in content

    def test_file_content_has_user_header(self, logger: SessionLogger) -> None:
        logger.new_session("S1")
        logger.log_user("User message")
        filepath = logger.flush()
        assert filepath is not None
        content = filepath.read_text(encoding="utf-8")
        assert "User message" in content

    def test_clears_entries_after_flush(self, logger: SessionLogger) -> None:
        logger.new_session("S1")
        logger.log_agent("content")
        logger.flush()
        assert logger.entries == []

    def test_clears_pending_summary_after_flush(self, logger: SessionLogger) -> None:
        logger.new_session("S1")
        logger._pending_summary = "some summary"
        logger.log_agent("content")
        logger.flush()
        assert logger._pending_summary is None

    def test_returns_none_if_no_entries(self, logger: SessionLogger) -> None:
        result = logger.flush()
        assert result is None

    def test_returns_none_if_no_stage(self, logger: SessionLogger) -> None:
        logger.log_agent("content")
        result = logger.flush()
        assert result is None

    def test_multiple_flushes_append_same_day(
        self, logger: SessionLogger, session_dir: Path
    ) -> None:
        """Same-day same-stage flushes append (separated by '---'), not overwrite."""
        logger.new_session("S1")
        logger.log_agent("First batch")
        logger.flush()

        # Continue same session stage (do NOT call new_session, which would
        # also flush — we want to test two flushes on the same buffer-state).
        logger.current_stage = "S1"
        logger.log_agent("Second batch")
        logger.flush()

        filepath = session_dir / f"{_today_utc()}_S1.md"
        content = filepath.read_text(encoding="utf-8")
        # Append semantics: both batches preserved.
        assert "First batch" in content
        assert "Second batch" in content
        # Separator between blocks.
        assert "\n---\n" in content

    def test_flush_includes_summary_section_when_pending(
        self, logger: SessionLogger
    ) -> None:
        """A pre-set _pending_summary is rendered at the top of the block."""
        logger.new_session("S1")
        logger.log_agent("dialog content")
        logger._pending_summary = "Pre-set summary text"
        filepath = logger.flush()
        assert filepath is not None
        content = filepath.read_text(encoding="utf-8")
        # Summary section header appears at the top.
        assert content.startswith("## ")
        assert "Pre-set summary text" in content
        # Dialog section follows.
        assert "### " in content
        assert "dialog content" in content

    def test_flush_includes_not_generated_marker_when_no_summary(
        self, logger: SessionLogger
    ) -> None:
        """When no summary was generated, the '未生成摘要' marker is used."""
        logger.new_session("S1")
        logger.log_agent("dialog content")
        filepath = logger.flush()
        assert filepath is not None
        content = filepath.read_text(encoding="utf-8")
        # The 'summary not generated' marker (zh) should appear.
        assert "未生成摘要" in content

    def test_flush_skips_system_entries_in_dialog(
        self, logger: SessionLogger
    ) -> None:
        """System entries (the new_session marker) are not rendered in the dialog."""
        logger.new_session("S1")  # adds a system entry
        logger.log_agent("real dialog")
        filepath = logger.flush()
        assert filepath is not None
        content = filepath.read_text(encoding="utf-8")
        # The system marker "新会话" should not appear in the dialog record.
        # (It may appear in t("session.new_session") = "新会话: 阶段 S1".)
        assert "新会话: 阶段 S1" not in content
        # But the real dialog is preserved.
        assert "real dialog" in content

    def test_flush_includes_timestamps_for_entries(
        self, logger: SessionLogger
    ) -> None:
        """Agent/user entries are rendered with bracketed timestamps."""
        logger.new_session("S1")
        logger.log_agent("agent says")
        logger.log_user("user replies")
        filepath = logger.flush()
        assert filepath is not None
        content = filepath.read_text(encoding="utf-8")
        # ISO timestamps contain 'T'; both entries should carry one.
        # The bracketed timestamp format is [<iso>].
        assert "[20" in content  # year prefix
        # Both dialog contents preserved.
        assert "agent says" in content
        assert "user replies" in content


class TestGetSessionFile:
    """Tests for get_session_file method (now date-based naming)."""

    def test_with_stage(self, logger: SessionLogger, session_dir: Path) -> None:
        logger.new_session("S3")
        filepath = logger.get_session_file()
        assert filepath == session_dir / f"{_today_utc()}_S3.md"

    def test_without_stage(self, logger: SessionLogger, session_dir: Path) -> None:
        filepath = logger.get_session_file()
        assert filepath == session_dir / "session.md"


class TestGetEntries:
    """Tests for get_entries method."""

    def test_empty(self, logger: SessionLogger) -> None:
        assert logger.get_entries() == []

    def test_returns_copy(self, logger: SessionLogger) -> None:
        logger.log_agent("content")
        entries = logger.get_entries()
        entries.clear()
        # Original should be unaffected
        assert len(logger.entries) == 1


class TestClear:
    """Tests for clear method."""

    def test_clears_entries(self, logger: SessionLogger) -> None:
        logger.log_agent("content1")
        logger.log_user("content2")
        logger.clear()
        assert logger.entries == []

    def test_preserves_stage(self, logger: SessionLogger) -> None:
        logger.new_session("S1")
        logger.clear()
        assert logger.current_stage == "S1"

    def test_clears_pending_summary(self, logger: SessionLogger) -> None:
        logger._pending_summary = "some summary"
        logger.clear()
        assert logger._pending_summary is None


class TestFinalizeSummary:
    """Tests for finalize_summary (Task D1)."""

    def test_generates_summary_via_llm(
        self, logger: SessionLogger, mock_llm: MagicMock
    ) -> None:
        logger.new_session("S1")
        logger.log_agent("We discussed the report audience.")
        logger.log_user("Yes, audience is the data team.")

        summary = logger.finalize_summary(mock_llm, "reasoning")

        assert summary == "Mock summary of the conversation."
        assert logger._pending_summary == "Mock summary of the conversation."
        mock_llm.chat.assert_called_once()
        # The role passed positionally.
        role_arg = mock_llm.chat.call_args.args[0]
        assert role_arg == "reasoning"

    def test_summary_prompt_includes_dialog_text(
        self, logger: SessionLogger, mock_llm: MagicMock
    ) -> None:
        logger.new_session("S1")
        logger.log_agent("Important point about Q3 revenue.")
        logger.finalize_summary(mock_llm, "reasoning")

        _role, messages = mock_llm.chat.call_args.args
        user_msg = messages[-1]["content"]
        assert "Important point about Q3 revenue." in user_msg

    def test_returns_empty_when_no_entries(
        self, logger: SessionLogger, mock_llm: MagicMock
    ) -> None:
        summary = logger.finalize_summary(mock_llm, "reasoning")
        assert summary == ""
        assert logger._pending_summary == ""
        # LLM should not be called when there is nothing to summarize.
        mock_llm.chat.assert_not_called()

    def test_flush_after_finalize_summary_writes_summary_at_top(
        self, logger: SessionLogger, mock_llm: MagicMock, session_dir: Path
    ) -> None:
        """The pending summary is embedded at the top of the flushed file."""
        mock_llm.chat.return_value = "用户确认了 Q3 受众为数据团队。"
        logger.new_session("S4")
        logger.log_agent("discussed audience")
        logger.log_user("confirmed data team")

        summary = logger.finalize_summary(mock_llm, "analysis")
        assert summary == "用户确认了 Q3 受众为数据团队。"

        filepath = logger.flush()
        assert filepath is not None
        content = filepath.read_text(encoding="utf-8")
        # The summary text should appear at the top of the file.
        assert content.startswith("## 核心摘要\n用户确认了 Q3 受众为数据团队。")
        # Dialog record should follow.
        assert "### 对话记录" in content
        assert "discussed audience" in content
        assert "confirmed data team" in content

    def test_handles_none_llm_response(
        self, logger: SessionLogger, mock_llm: MagicMock
    ) -> None:
        """A None LLM response is defensively treated as empty summary."""
        mock_llm.chat.return_value = None
        logger.new_session("S1")
        logger.log_agent("content")
        summary = logger.finalize_summary(mock_llm, "reasoning")
        assert summary == ""
        assert logger._pending_summary == ""


class TestGetFullText:
    """Tests for get_full_text (Task D1)."""

    def test_empty_when_no_entries(self, logger: SessionLogger) -> None:
        assert logger.get_full_text() == ""

    def test_skips_system_entries(self, logger: SessionLogger) -> None:
        """System entries are not included in the plain-text rendering."""
        logger.new_session("S1")  # adds a system entry
        text = logger.get_full_text()
        # Only the system entry is present, so output is empty.
        assert text == ""

    def test_renders_agent_and_user_lines(self, logger: SessionLogger) -> None:
        logger.new_session("S1")
        logger.log_agent("Agent message here.")
        logger.log_user("User reply here.")

        text = logger.get_full_text()
        lines = text.split("\n")
        assert len(lines) == 2
        # Each line is "角色: 内容".
        assert lines[0] == "Agent: Agent message here."
        assert lines[1] == "用户: User reply here."

    def test_order_preserved(self, logger: SessionLogger) -> None:
        logger.log_user("first")
        logger.log_agent("second")
        logger.log_user("third")

        text = logger.get_full_text()
        lines = text.split("\n")
        assert lines[0].endswith(": first")
        assert lines[1].endswith(": second")
        assert lines[2].endswith(": third")

    def test_used_by_finalize_summary(
        self, logger: SessionLogger, mock_llm: MagicMock
    ) -> None:
        """finalize_summary feeds get_full_text() output to the LLM."""
        logger.new_session("S2")
        logger.log_agent("S2 dialog content XYZ")
        logger.finalize_summary(mock_llm, "reasoning")

        _role, messages = mock_llm.chat.call_args.args
        user_msg = messages[-1]["content"]
        # The system entry is stripped, only agent/user lines included.
        assert "S2 dialog content XYZ" in user_msg
        # System marker (from new_session) should not be in the prompt.
        assert "新会话: 阶段 S2" not in user_msg


class TestReadHistory:
    """Tests for read_history module-level function (Task D3)."""

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        result = read_history(tmp_path / "nonexistent")
        assert result == ""

    def test_returns_empty_when_no_matching_files(
        self, session_dir: Path
    ) -> None:
        result = read_history(session_dir, target="S9")
        assert result == ""

    def test_returns_empty_when_dir_empty(self, session_dir: Path) -> None:
        result = read_history(session_dir, target="all")
        assert result == ""

    def test_target_all_returns_all_files_sorted(
        self, session_dir: Path
    ) -> None:
        """target='all' returns every .md file, sorted by filename."""
        (session_dir / "2026-07-22_S4.md").write_text("S4 day 1 content", encoding="utf-8")
        (session_dir / "2026-07-21_S1.md").write_text("S1 day 0 content", encoding="utf-8")
        (session_dir / "2026-07-23_S4.md").write_text("S4 day 2 content", encoding="utf-8")

        result = read_history(session_dir, target="all")
        # Sorted by filename: 2026-07-21_S1.md, 2026-07-22_S4.md, 2026-07-23_S4.md
        idx_s1 = result.find("S1 day 0 content")
        idx_s4_d1 = result.find("S4 day 1 content")
        idx_s4_d2 = result.find("S4 day 2 content")
        assert idx_s1 != -1 and idx_s4_d1 != -1 and idx_s4_d2 != -1
        assert idx_s1 < idx_s4_d1 < idx_s4_d2
        # Separator between files.
        assert "\n---\n" in result

    def test_target_all_includes_legacy_named_files(
        self, session_dir: Path
    ) -> None:
        """Legacy <stage>_session.md files are included under target='all'."""
        (session_dir / "S2_session.md").write_text("legacy S2 content", encoding="utf-8")
        (session_dir / "2026-07-22_S4.md").write_text("new S4 content", encoding="utf-8")

        result = read_history(session_dir, target="all")
        assert "legacy S2 content" in result
        assert "new S4 content" in result

    def test_target_stage_matches_new_naming(self, session_dir: Path) -> None:
        """Stage target matches YYYY-MM-DD_<stage>.md files for that stage."""
        (session_dir / "2026-07-22_S4.md").write_text("S4 content", encoding="utf-8")
        (session_dir / "2026-07-22_S1.md").write_text("S1 content", encoding="utf-8")
        (session_dir / "2026-07-23_S4.md").write_text("S4 second day", encoding="utf-8")

        result = read_history(session_dir, target="S4")
        assert "S4 content" in result
        assert "S4 second day" in result
        # S1 file should NOT be included.
        assert "S1 content" not in result

    def test_target_stage_matches_legacy_naming(self, session_dir: Path) -> None:
        """Stage target also matches legacy <stage>_session.md."""
        (session_dir / "S2_session.md").write_text("legacy S2 content", encoding="utf-8")
        (session_dir / "2026-07-22_S4.md").write_text("S4 content", encoding="utf-8")

        result = read_history(session_dir, target="S2")
        assert "legacy S2 content" in result
        assert "S4 content" not in result

    def test_target_stage_matches_both_new_and_legacy(
        self, session_dir: Path
    ) -> None:
        """Stage target matches both legacy and new-naming files for that stage."""
        (session_dir / "S4_session.md").write_text("legacy S4 content", encoding="utf-8")
        (session_dir / "2026-07-22_S4.md").write_text("new S4 content", encoding="utf-8")

        result = read_history(session_dir, target="S4")
        assert "legacy S4 content" in result
        assert "new S4 content" in result

    def test_target_date_matches_prefix(self, session_dir: Path) -> None:
        """Date target matches files whose name starts with the date."""
        (session_dir / "2026-07-22_S1.md").write_text("S1 on 22nd", encoding="utf-8")
        (session_dir / "2026-07-22_S4.md").write_text("S4 on 22nd", encoding="utf-8")
        (session_dir / "2026-07-23_S4.md").write_text("S4 on 23rd", encoding="utf-8")

        result = read_history(session_dir, target="2026-07-22")
        assert "S1 on 22nd" in result
        assert "S4 on 22nd" in result
        # Different date should not be included.
        assert "S4 on 23rd" not in result

    def test_target_date_sorts_files(self, session_dir: Path) -> None:
        """Date-matched files are returned sorted by filename."""
        (session_dir / "2026-07-22_S4.md").write_text("second file", encoding="utf-8")
        (session_dir / "2026-07-22_S1.md").write_text("first file", encoding="utf-8")

        result = read_history(session_dir, target="2026-07-22")
        idx_first = result.find("first file")
        idx_second = result.find("second file")
        assert idx_first < idx_second

    def test_default_target_is_all(self, session_dir: Path) -> None:
        """When target is omitted, the default is 'all'."""
        (session_dir / "2026-07-22_S1.md").write_text("content here", encoding="utf-8")

        result = read_history(session_dir)
        assert "content here" in result

    def test_empty_string_target_treated_as_all(
        self, session_dir: Path
    ) -> None:
        """An empty target string is treated as 'all'."""
        (session_dir / "2026-07-22_S1.md").write_text("content here", encoding="utf-8")

        result = read_history(session_dir, target="")
        assert "content here" in result

    def test_ignores_non_markdown_files(self, session_dir: Path) -> None:
        """Non-.md files are ignored even when target='all'."""
        (session_dir / "2026-07-22_S1.md").write_text("md content", encoding="utf-8")
        (session_dir / "notes.txt").write_text("txt content", encoding="utf-8")
        (session_dir / "README.md").write_text("readme content", encoding="utf-8")

        result = read_history(session_dir, target="all")
        # Both .md files are included.
        assert "md content" in result
        assert "readme content" in result
        # Non-markdown file is excluded.
        assert "txt content" not in result

    def test_concatenated_result_ends_with_newline(
        self, session_dir: Path
    ) -> None:
        """The concatenated result is terminated with a newline."""
        (session_dir / "2026-07-22_S1.md").write_text("single file content", encoding="utf-8")

        result = read_history(session_dir, target="all")
        assert result.endswith("\n")
