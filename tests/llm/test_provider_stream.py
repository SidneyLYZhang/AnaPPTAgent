"""Tests for streaming methods (chat_stream / chat_with_tools_stream)."""

from __future__ import annotations

import types
from unittest.mock import patch

import pytest

from anappt.io.config import ModelRoleConfig, ModelsConfig
from anappt.llm.provider import AnaPPTLLM


@pytest.fixture
def models_config():
    """Create a test ModelsConfig."""
    return ModelsConfig(
        reasoning=ModelRoleConfig(
            provider="deepseek", model="deepseek-reasoner", api_key="test-key-r"
        ),
        analysis=ModelRoleConfig(
            provider="openai", model="gpt-4o", api_key="test-key-a"
        ),
        writing=ModelRoleConfig(
            provider="anthropic", model="claude-sonnet-4-20250514", api_key="test-key-w"
        ),
    )


@pytest.fixture
def llm(models_config):
    """Create a test AnaPPTLLM."""
    return AnaPPTLLM(models_config)


def _make_delta(
    content=None,
    reasoning=None,
    tool_calls=None,
):
    """Build a fake streaming delta with all standard fields set."""
    return types.SimpleNamespace(
        content=content,
        reasoning_content=reasoning,
        tool_calls=tool_calls,
    )


def _make_chunk(delta):
    """Wrap a delta into a fake streaming chunk with choices[0].delta."""
    choice = types.SimpleNamespace(delta=delta)
    return types.SimpleNamespace(choices=[choice])


def _make_tool_call_delta(
    index,
    id=None,
    name=None,
    arguments=None,
):
    """Build a fake ChoiceDeltaToolCall fragment."""
    function = types.SimpleNamespace(name=name, arguments=arguments)
    return types.SimpleNamespace(index=index, id=id, function=function)


class TestChatStream:
    """Test the chat_stream() method."""

    @patch("anappt.llm.provider.litellm")
    def test_chat_stream_content_and_reasoning(self, mock_litellm, llm):
        """chat_stream yields reasoning before content, concatenating to full text."""
        chunks = [
            _make_chunk(_make_delta(reasoning="Let me think")),
            _make_chunk(_make_delta(reasoning=" about this")),
            _make_chunk(_make_delta(content="Hello")),
            _make_chunk(_make_delta(content=" world")),
            _make_chunk(_make_delta()),  # None/None -> no yield
        ]
        mock_litellm.completion.return_value = chunks

        messages = [{"role": "user", "content": "Hi"}]
        result = list(llm.chat_stream("reasoning", messages))

        # Reasoning fragments come first, then content fragments
        assert result == ["Let me think", " about this", "Hello", " world"]
        # Concatenation yields the full text
        assert "".join(result) == "Let me think about thisHello world"

        mock_litellm.completion.assert_called_once()
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["stream"] is True
        assert call_kwargs["model"] == "deepseek/deepseek-reasoner"
        assert call_kwargs["messages"] == messages


class TestChatWithToolsStream:
    """Test the chat_with_tools_stream() method."""

    @patch("anappt.llm.provider.litellm")
    def test_chat_with_tools_stream_content(self, mock_litellm, llm):
        """Pure content stream yields content events in order."""
        chunks = [
            _make_chunk(_make_delta(content="Hello")),
            _make_chunk(_make_delta(content=" world")),
        ]
        mock_litellm.completion.return_value = chunks

        tools = [{"type": "function", "function": {"name": "search"}}]
        events = list(
            llm.chat_with_tools_stream(
                "analysis", [{"role": "user", "content": "hi"}], tools
            )
        )

        assert events == [
            {"type": "content", "delta": "Hello"},
            {"type": "content", "delta": " world"},
        ]
        mock_litellm.completion.assert_called_once()
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["stream"] is True
        assert call_kwargs["tools"] == tools

    @patch("anappt.llm.provider.litellm")
    def test_chat_with_tools_stream_tool_calls(self, mock_litellm, llm):
        """Tool call fragments are yielded per chunk (name on first, args split)."""
        tc_first = _make_tool_call_delta(index=0, id="call_1", name="search_web")
        tc_args1 = _make_tool_call_delta(index=0, arguments='{"q":')
        tc_args2 = _make_tool_call_delta(index=0, arguments=' "python"}')

        chunks = [
            _make_chunk(_make_delta(tool_calls=[tc_first])),
            _make_chunk(_make_delta(tool_calls=[tc_args1])),
            _make_chunk(_make_delta(tool_calls=[tc_args2])),
        ]
        mock_litellm.completion.return_value = chunks

        tools = [{"type": "function", "function": {"name": "search_web"}}]
        events = list(
            llm.chat_with_tools_stream(
                "analysis", [{"role": "user", "content": "search"}], tools
            )
        )

        assert len(events) == 3
        # First chunk: name present, arguments absent (None)
        assert events[0] == {
            "type": "tool_call",
            "tool_call": {
                "index": 0,
                "id": "call_1",
                "name": "search_web",
                "arguments": None,
            },
        }
        # Second chunk: arguments fragment 1, id/name absent (None)
        assert events[1] == {
            "type": "tool_call",
            "tool_call": {
                "index": 0,
                "id": None,
                "name": None,
                "arguments": '{"q":',
            },
        }
        # Third chunk: arguments fragment 2, id/name absent (None)
        assert events[2] == {
            "type": "tool_call",
            "tool_call": {
                "index": 0,
                "id": None,
                "name": None,
                "arguments": ' "python"}',
            },
        }

        # Verify the arguments can be accumulated by the caller
        accumulated_args = "".join(
            e["tool_call"]["arguments"]
            for e in events
            if e["type"] == "tool_call" and e["tool_call"]["arguments"]
        )
        assert accumulated_args == '{"q": "python"}'

    @patch("anappt.llm.provider.litellm")
    def test_chat_with_tools_stream_mixed(self, mock_litellm, llm):
        """Content and tool_call events can interleave within a stream."""
        tc = _make_tool_call_delta(index=0, id="call_1", name="render_deck")
        chunks = [
            _make_chunk(_make_delta(content="Let me render")),
            _make_chunk(_make_delta(tool_calls=[tc])),
            _make_chunk(_make_delta(content=" done")),
        ]
        mock_litellm.completion.return_value = chunks

        tools = [{"type": "function", "function": {"name": "render_deck"}}]
        events = list(
            llm.chat_with_tools_stream(
                "writing", [{"role": "user", "content": "go"}], tools
            )
        )

        assert events == [
            {"type": "content", "delta": "Let me render"},
            {
                "type": "tool_call",
                "tool_call": {
                    "index": 0,
                    "id": "call_1",
                    "name": "render_deck",
                    "arguments": None,
                },
            },
            {"type": "content", "delta": " done"},
        ]
