"""Tests for MemoryManager (Task D2)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.memory import MemoryManager


@pytest.fixture
def memory_file(tmp_path: Path) -> Path:
    """Return the path to a (not-yet-existing) memory.md inside tmp_path."""
    return tmp_path / ".anappt" / "memory.md"


@pytest.fixture
def mock_llm() -> MagicMock:
    """Return a mock AnaPPTLLM with a configurable chat return value."""
    mock = MagicMock()
    mock.chat.return_value = "updated memory content"
    return mock


class TestRead:
    """Tests for MemoryManager.read."""

    def test_read_nonexistent_returns_empty(self, memory_file: Path) -> None:
        mgr = MemoryManager(memory_file)
        assert mgr.read() == ""
        assert not memory_file.exists()

    def test_read_existing_file(self, memory_file: Path) -> None:
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_file.write_text("# Project Memory\n\n- audience confirmed\n", encoding="utf-8")

        mgr = MemoryManager(memory_file)
        assert mgr.read() == "# Project Memory\n\n- audience confirmed\n"

    def test_read_empty_file(self, memory_file: Path) -> None:
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_file.write_text("", encoding="utf-8")

        mgr = MemoryManager(memory_file)
        assert mgr.read() == ""

    def test_read_preserves_path_attribute(self, memory_file: Path) -> None:
        mgr = MemoryManager(memory_file)
        assert mgr.memory_file == memory_file


class TestUpdate:
    """Tests for MemoryManager.update."""

    def test_update_writes_content_when_llm_returns_update(
        self, memory_file: Path, mock_llm: MagicMock
    ) -> None:
        """When the LLM returns new memory content, the file is written and True returned.

        The manager strips surrounding whitespace from the LLM response
        before writing, so trailing newlines are not preserved.
        """
        new_content = (
            "# Project Memory\n\n"
            "## 2026-07-22\n- audience: data team\n- goal: quarterly review"
        )
        # LLM response with trailing whitespace — should be stripped on write.
        mock_llm.chat.return_value = new_content + "\n\n"

        mgr = MemoryManager(memory_file)
        result = mgr.update(mock_llm, "reasoning", "Agent: confirmed audience")

        assert result is True
        assert memory_file.exists()
        assert memory_file.read_text(encoding="utf-8") == new_content

    def test_update_no_update_token_returns_false(
        self, memory_file: Path, mock_llm: MagicMock
    ) -> None:
        """When the LLM returns 'NO_UPDATE', no file is written and False returned."""
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_file.write_text("existing memory", encoding="utf-8")

        mock_llm.chat.return_value = "NO_UPDATE"
        mgr = MemoryManager(memory_file)
        result = mgr.update(mock_llm, "reasoning", "User: hello")

        assert result is False
        # Existing file untouched.
        assert memory_file.read_text(encoding="utf-8") == "existing memory"

    def test_update_no_update_token_with_whitespace_returns_false(
        self, memory_file: Path, mock_llm: MagicMock
    ) -> None:
        """A 'NO_UPDATE' token surrounded by whitespace still triggers no write."""
        mock_llm.chat.return_value = "  NO_UPDATE  \n"
        mgr = MemoryManager(memory_file)
        result = mgr.update(mock_llm, "reasoning", "session text")

        assert result is False
        assert not memory_file.exists()

    def test_update_no_update_lowercase_returns_false(
        self, memory_file: Path, mock_llm: MagicMock
    ) -> None:
        """Case-insensitive 'no_update' should also be treated as no-update."""
        mock_llm.chat.return_value = "no_update"
        mgr = MemoryManager(memory_file)
        result = mgr.update(mock_llm, "reasoning", "session text")

        assert result is False
        assert not memory_file.exists()

    def test_update_blank_response_returns_false(
        self, memory_file: Path, mock_llm: MagicMock
    ) -> None:
        """A blank LLM response is treated as no update."""
        mock_llm.chat.return_value = ""
        mgr = MemoryManager(memory_file)
        result = mgr.update(mock_llm, "reasoning", "session text")

        assert result is False
        assert not memory_file.exists()

    def test_update_whitespace_only_response_returns_false(
        self, memory_file: Path, mock_llm: MagicMock
    ) -> None:
        """A whitespace-only LLM response is treated as no update."""
        mock_llm.chat.return_value = "   \n\t  "
        mgr = MemoryManager(memory_file)
        result = mgr.update(mock_llm, "reasoning", "session text")

        assert result is False
        assert not memory_file.exists()

    def test_update_none_response_returns_false(
        self, memory_file: Path, mock_llm: MagicMock
    ) -> None:
        """A None LLM response (defensive) is treated as no update."""
        mock_llm.chat.return_value = None
        mgr = MemoryManager(memory_file)
        result = mgr.update(mock_llm, "reasoning", "session text")

        assert result is False

    def test_update_creates_parent_directory(
        self, memory_file: Path, mock_llm: MagicMock
    ) -> None:
        """When the parent directory does not yet exist, it is created on write."""
        mock_llm.chat.return_value = "new memory"
        mgr = MemoryManager(memory_file)
        # Parent .anappt/ does not exist yet.
        assert not memory_file.parent.exists()

        result = mgr.update(mock_llm, "reasoning", "session text")

        assert result is True
        assert memory_file.exists()
        assert memory_file.parent.is_dir()

    def test_update_sends_current_memory_in_prompt(
        self, memory_file: Path, mock_llm: MagicMock
    ) -> None:
        """The current memory text is included in the user prompt sent to the LLM."""
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_file.write_text("EXISTING_MEMORY_CONTENT", encoding="utf-8")

        mock_llm.chat.return_value = "NO_UPDATE"
        mgr = MemoryManager(memory_file)
        mgr.update(mock_llm, "reasoning", "SESSION_CONTENT")

        mock_llm.chat.assert_called_once()
        _role, messages = mock_llm.chat.call_args.args
        # First positional arg is the role.
        assert _role == "reasoning"
        user_msg = messages[-1]["content"]
        assert "EXISTING_MEMORY_CONTENT" in user_msg
        assert "SESSION_CONTENT" in user_msg

    def test_update_overwrites_existing_file(
        self, memory_file: Path, mock_llm: MagicMock
    ) -> None:
        """When the LLM returns new content, the existing file is fully replaced."""
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_file.write_text("old content that should be replaced", encoding="utf-8")

        mock_llm.chat.return_value = "new content"
        mgr = MemoryManager(memory_file)
        result = mgr.update(mock_llm, "reasoning", "session text")

        assert result is True
        assert memory_file.read_text(encoding="utf-8") == "new content"


class TestAppend:
    """Tests for MemoryManager.append (incremental, LLM-free memory writes)."""

    def test_append_creates_file_with_date_prefix(self, memory_file: Path) -> None:
        """Appending a non-empty entry writes a ``## YYYY-MM-DD`` header + body."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        mgr = MemoryManager(memory_file)
        result = mgr.append("受众已确认为数据团队")

        assert result is True
        assert memory_file.exists()
        content = memory_file.read_text(encoding="utf-8")
        assert f"## {today}" in content
        assert "受众已确认为数据团队" in content

    def test_append_creates_file_when_not_exists(self, tmp_path: Path) -> None:
        """When the memory file does not yet exist, append creates it."""
        fresh = tmp_path / ".anappt" / "memory.md"
        assert not fresh.exists()

        mgr = MemoryManager(fresh)
        result = mgr.append("first entry")

        assert result is True
        assert fresh.exists()
        assert "first entry" in fresh.read_text(encoding="utf-8")

    def test_append_creates_parent_directory(self, memory_file: Path) -> None:
        """When the parent directory does not yet exist, it is created."""
        assert not memory_file.parent.exists()

        mgr = MemoryManager(memory_file)
        result = mgr.append("parent dir auto-created")

        assert result is True
        assert memory_file.parent.is_dir()
        assert memory_file.exists()

    def test_append_two_entries_both_present(self, memory_file: Path) -> None:
        """Two successive appends both survive, each with its own date header."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        mgr = MemoryManager(memory_file)
        mgr.append("first decision")
        mgr.append("second decision")

        content = memory_file.read_text(encoding="utf-8")
        # Both entries present (no overwrite).
        assert "first decision" in content
        assert "second decision" in content
        # Each has its own date header — count occurrences of today's header.
        assert content.count(f"## {today}") == 2
        # Ordering: first entry comes before second.
        assert content.index("first decision") < content.index("second decision")

    def test_append_empty_entry_returns_false(self, memory_file: Path) -> None:
        """An empty string entry is skipped; returns False and writes nothing."""
        mgr = MemoryManager(memory_file)
        result = mgr.append("")

        assert result is False
        assert not memory_file.exists()

    def test_append_whitespace_only_entry_returns_false(
        self, memory_file: Path
    ) -> None:
        """A whitespace-only entry is stripped to empty and skipped."""
        mgr = MemoryManager(memory_file)
        result = mgr.append("   \n\t  ")

        assert result is False
        assert not memory_file.exists()

    def test_append_returns_true_on_success(self, memory_file: Path) -> None:
        """A successful append returns True."""
        mgr = MemoryManager(memory_file)
        assert mgr.append("a real entry") is True

    def test_append_preserves_existing_content_and_appends_at_end(
        self, memory_file: Path
    ) -> None:
        """Appending to a non-empty file keeps old content and adds a separator
        plus the new block at the end."""
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_file.write_text("# Project Memory\n\n- old note", encoding="utf-8")

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        mgr = MemoryManager(memory_file)
        result = mgr.append("new finding")

        assert result is True
        content = memory_file.read_text(encoding="utf-8")
        # Old content still present.
        assert "# Project Memory" in content
        assert "old note" in content
        # New entry at the end with today's header.
        assert content.endswith(f"## {today}\nnew finding")
        # A separator (blank line) exists between old and new content.
        assert "old note\n\n## " in content

    def test_append_strips_entry_whitespace(self, memory_file: Path) -> None:
        """Leading/trailing whitespace on the entry is stripped before writing."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        mgr = MemoryManager(memory_file)
        mgr.append("   padded entry   ")

        content = memory_file.read_text(encoding="utf-8")
        assert f"## {today}\npadded entry" in content
