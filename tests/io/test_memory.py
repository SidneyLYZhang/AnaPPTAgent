"""Tests for MemoryManager (Task D2)."""

from __future__ import annotations

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
