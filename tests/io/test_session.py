"""Tests for SessionLogger."""

from __future__ import annotations

from pathlib import Path

import pytest

from anappt.io.session import SessionLogger


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
        # S1 session file should exist
        s1_file = session_dir / "S1_session.md"
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
    """Tests for flush method."""

    def test_writes_file(self, logger: SessionLogger, session_dir: Path) -> None:
        logger.new_session("S1")
        logger.log_agent("Test content")
        result = logger.flush()
        assert result is not None
        assert result.exists()
        assert result == session_dir / "S1_session.md"

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

    def test_returns_none_if_no_entries(self, logger: SessionLogger) -> None:
        result = logger.flush()
        assert result is None

    def test_returns_none_if_no_stage(self, logger: SessionLogger) -> None:
        logger.log_agent("content")
        result = logger.flush()
        assert result is None

    def test_multiple_flushes(self, logger: SessionLogger, session_dir: Path) -> None:
        logger.new_session("S1")
        logger.log_agent("First batch")
        logger.flush()

        logger.log_agent("Second batch")
        logger.flush()

        filepath = session_dir / "S1_session.md"
        content = filepath.read_text(encoding="utf-8")
        assert "Second batch" in content
        # Second flush overwrites file, so first batch should not be in content
        assert "First batch" not in content


class TestGetSessionFile:
    """Tests for get_session_file method."""

    def test_with_stage(self, logger: SessionLogger, session_dir: Path) -> None:
        logger.new_session("S3")
        filepath = logger.get_session_file()
        assert filepath == session_dir / "S3_session.md"

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
