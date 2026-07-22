"""Tests for the LLM provider module."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from anappt.io.config import (
    ModelRoleConfig,
    ModelsConfig,
    WebFetchConfig,
    WebSearchConfig,
)
from anappt.llm.provider import (
    AnaPPTLLM,
    load_global_config,
    save_global_config,
)


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


class TestAnaPPTLLMInit:
    """Test AnaPPTLLM initialization."""

    def test_init_stores_config(self, llm, models_config):
        assert llm.config is models_config

    def test_init_maps_roles(self, llm):
        assert llm._models["reasoning"].model == "deepseek-reasoner"
        assert llm._models["analysis"].model == "gpt-4o"
        assert llm._models["writing"].model == "claude-sonnet-4-20250514"


class TestModelForRole:
    """Test role-to-model mapping."""

    def test_reasoning_role(self, llm):
        config = llm._model_for_role("reasoning")
        assert config.model == "deepseek-reasoner"

    def test_analysis_role(self, llm):
        config = llm._model_for_role("analysis")
        assert config.model == "gpt-4o"

    def test_writing_role(self, llm):
        config = llm._model_for_role("writing")
        assert config.model == "claude-sonnet-4-20250514"

    def test_invalid_role_raises(self, llm):
        with pytest.raises(ValueError, match="Invalid model role"):
            llm._model_for_role("invalid")


class TestChat:
    """Test the chat() method."""

    @patch("anappt.llm.provider.litellm")
    def test_chat_calls_litellm_completion(self, mock_litellm, llm):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from LLM"
        mock_litellm.completion.return_value = mock_response

        messages = [{"role": "user", "content": "Hi"}]
        result = llm.chat("reasoning", messages)

        assert result == "Hello from LLM"
        mock_litellm.completion.assert_called_once()

        call_kwargs = mock_litellm.completion.call_args
        assert call_kwargs.kwargs["model"] == "deepseek-reasoner"
        assert call_kwargs.kwargs["api_key"] == "test-key-r"

    @patch("anappt.llm.provider.litellm")
    def test_chat_passes_messages(self, mock_litellm, llm):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"
        mock_litellm.completion.return_value = mock_response

        messages = [{"role": "user", "content": "Test message"}]
        llm.chat("analysis", messages)

        call_kwargs = mock_litellm.completion.call_args
        assert call_kwargs.kwargs["messages"] == messages

    @patch("anappt.llm.provider.litellm")
    def test_chat_with_api_base(self, mock_litellm):
        config = ModelsConfig(
            reasoning=ModelRoleConfig(
                provider="custom",
                model="custom-model",
                api_base="https://custom.api.com/v1",
                api_key="key",
            )
        )
        llm = AnaPPTLLM(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "OK"
        mock_litellm.completion.return_value = mock_response

        llm.chat("reasoning", [{"role": "user", "content": "test"}])

        call_kwargs = mock_litellm.completion.call_args
        assert call_kwargs.kwargs["api_base"] == "https://custom.api.com/v1"

    @patch("anappt.llm.provider.litellm")
    def test_chat_returns_empty_string_on_none_content(self, mock_litellm, llm):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_litellm.completion.return_value = mock_response

        result = llm.chat("writing", [{"role": "user", "content": "test"}])
        assert result == ""


class TestChatWithTools:
    """Test the chat_with_tools() method."""

    @patch("anappt.llm.provider.litellm")
    def test_chat_with_tools_returns_content(self, mock_litellm, llm):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Analysis complete"
        mock_response.choices[0].message.tool_calls = None
        mock_litellm.completion.return_value = mock_response

        messages = [{"role": "user", "content": "Analyze data"}]
        tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
        result = llm.chat_with_tools("analysis", messages, tools)

        assert result["content"] == "Analysis complete"
        assert result["tool_calls"] == []

    @patch("anappt.llm.provider.litellm")
    def test_chat_with_tools_parses_tool_calls(self, mock_litellm, llm):
        mock_tc = MagicMock()
        mock_tc.id = "call_123"
        mock_tc.function.name = "search_web"
        mock_tc.function.arguments = '{"query": "python"}'

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.choices[0].message.tool_calls = [mock_tc]
        mock_litellm.completion.return_value = mock_response

        result = llm.chat_with_tools(
            "analysis",
            [{"role": "user", "content": "search"}],
            [{"type": "function", "function": {"name": "search_web"}}],
        )

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["id"] == "call_123"
        assert result["tool_calls"][0]["name"] == "search_web"
        assert result["tool_calls"][0]["arguments"] == '{"query": "python"}'

    @patch("anappt.llm.provider.litellm")
    def test_chat_with_tools_passes_tools_param(self, mock_litellm, llm):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "done"
        mock_response.choices[0].message.tool_calls = None
        mock_litellm.completion.return_value = mock_response

        tools = [{"type": "function", "function": {"name": "test"}}]
        llm.chat_with_tools("analysis", [{"role": "user", "content": "test"}], tools)

        call_kwargs = mock_litellm.completion.call_args
        assert call_kwargs.kwargs["tools"] == tools


class TestThinkingMapping:
    """Test the ``thinking`` config field to LiteLLM params mapping."""

    def _make_llm(self, provider: str, thinking: str | int | bool | None) -> AnaPPTLLM:
        """Build an AnaPPTLLM whose reasoning role uses the given provider/thinking."""
        config = ModelsConfig(
            reasoning=ModelRoleConfig(
                provider=provider,
                model="test-model",
                api_key="test-key",
                thinking=thinking,
            )
        )
        return AnaPPTLLM(config)

    def _mock_completion(self, mock_litellm: Any) -> None:
        """Wire a minimal mock response into the patched litellm module."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_litellm.completion.return_value = mock_response

    @patch("anappt.llm.provider.litellm")
    def test_thinking_none_openai_passes_high(self, mock_litellm):
        llm = self._make_llm("openai", None)
        self._mock_completion(mock_litellm)

        llm.chat("reasoning", [{"role": "user", "content": "hi"}])
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["reasoning_effort"] == "high"

    @patch("anappt.llm.provider.litellm")
    def test_thinking_none_anthropic_passes_nothing(self, mock_litellm):
        llm = self._make_llm("anthropic", None)
        self._mock_completion(mock_litellm)

        llm.chat("reasoning", [{"role": "user", "content": "hi"}])
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert "reasoning_effort" not in call_kwargs
        assert "thinking" not in call_kwargs

    @patch("anappt.llm.provider.litellm")
    def test_thinking_false_openai_passes_minimal(self, mock_litellm):
        llm = self._make_llm("openai", "FALSE")
        self._mock_completion(mock_litellm)

        llm.chat("reasoning", [{"role": "user", "content": "hi"}])
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["reasoning_effort"] == "minimal"

    @patch("anappt.llm.provider.litellm")
    def test_thinking_false_case_insensitive(self, mock_litellm):
        llm = self._make_llm("openai", "off")
        self._mock_completion(mock_litellm)

        llm.chat("reasoning", [{"role": "user", "content": "hi"}])
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["reasoning_effort"] == "minimal"

    @patch("anappt.llm.provider.litellm")
    def test_thinking_high_openai(self, mock_litellm):
        llm = self._make_llm("openai", "high")
        self._mock_completion(mock_litellm)

        llm.chat("reasoning", [{"role": "user", "content": "hi"}])
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["reasoning_effort"] == "high"

    @patch("anappt.llm.provider.litellm")
    def test_thinking_medium_openai(self, mock_litellm):
        llm = self._make_llm("openai", "medium")
        self._mock_completion(mock_litellm)

        llm.chat("reasoning", [{"role": "user", "content": "hi"}])
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["reasoning_effort"] == "medium"

    @patch("anappt.llm.provider.litellm")
    def test_thinking_int_anthropic(self, mock_litellm):
        llm = self._make_llm("anthropic", 8000)
        self._mock_completion(mock_litellm)

        llm.chat("reasoning", [{"role": "user", "content": "hi"}])
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["thinking"] == {"type": "enabled", "budget_tokens": 8000}

    @patch("anappt.llm.provider.litellm")
    def test_thinking_int_openai_ignored(self, mock_litellm):
        llm = self._make_llm("openai", 8000)
        self._mock_completion(mock_litellm)

        llm.chat("reasoning", [{"role": "user", "content": "hi"}])
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert "thinking" not in call_kwargs
        assert "reasoning_effort" not in call_kwargs

    @patch("anappt.llm.provider.litellm")
    def test_thinking_false_anthropic_no_thinking(self, mock_litellm):
        llm = self._make_llm("anthropic", "FALSE")
        self._mock_completion(mock_litellm)

        llm.chat("reasoning", [{"role": "user", "content": "hi"}])
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert "thinking" not in call_kwargs

    @patch("anappt.llm.provider.litellm")
    def test_caller_kwargs_override_thinking(self, mock_litellm):
        llm = self._make_llm("openai", None)
        self._mock_completion(mock_litellm)

        llm.chat("reasoning", [{"role": "user", "content": "hi"}], reasoning_effort="low")
        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["reasoning_effort"] == "low"


class TestGlobalConfig:
    """Test global configuration management."""

    def test_load_global_config_nonexistent(self, monkeypatch, tmp_path):
        """Should return default config when file doesn't exist."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr("anappt.llm.provider.Path.home", lambda: tmp_path)
        config = load_global_config()
        assert config.reasoning.model == ""
        assert config.analysis.model == ""

    def test_load_global_config_from_file(self, monkeypatch, tmp_path):
        """Should load config from ~/.anappt/models.yaml."""
        anappt_dir = tmp_path / ".anappt"
        anappt_dir.mkdir()
        models_yaml = anappt_dir / "models.yaml"
        models_yaml.write_text(
            "reasoning:\n"
            "  provider: deepseek\n"
            "  model: deepseek-reasoner\n"
            "  api_key: test-key\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("anappt.llm.provider.Path.home", lambda: tmp_path)

        config = load_global_config()
        assert config.reasoning.model == "deepseek-reasoner"
        assert config.reasoning.api_key == "test-key"

    def test_load_global_config_with_thinking_and_web(self, monkeypatch, tmp_path):
        """load_global_config parses thinking and web_search/web_fetch sections."""
        anappt_dir = tmp_path / ".anappt"
        anappt_dir.mkdir()
        models_yaml = anappt_dir / "models.yaml"
        models_yaml.write_text(
            "reasoning:\n"
            "  provider: openai\n"
            "  model: o1\n"
            "  thinking: FALSE\n"
            "web_search:\n"
            "  backend: anysearch\n"
            "  anysearch_api_key: any-key\n"
            "web_fetch:\n"
            "  jina_api_key: test-jina\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("anappt.llm.provider.Path.home", lambda: tmp_path)

        config = load_global_config()
        assert config.reasoning.thinking is False
        assert config.web_search.backend == "anysearch"
        assert config.web_search.anysearch_api_key == "any-key"
        assert config.web_fetch.jina_api_key == "test-jina"

    def test_save_global_config(self, monkeypatch, tmp_path):
        monkeypatch.setattr("anappt.llm.provider.Path.home", lambda: tmp_path)

        config = ModelsConfig(
            reasoning=ModelRoleConfig(
                provider="deepseek",
                model="deepseek-reasoner",
                api_key="key",
                thinking="high",
            ),
            web_search=WebSearchConfig(backend="zai"),
            web_fetch=WebFetchConfig(jina_api_key="jk"),
        )
        saved_path = save_global_config(config)

        assert saved_path.exists()
        assert saved_path == tmp_path / ".anappt" / "models.yaml"

        # Verify it can be loaded back (thinking + web sections roundtrip)
        loaded = load_global_config()
        assert loaded.reasoning.model == "deepseek-reasoner"
        assert loaded.reasoning.api_key == "key"
        assert loaded.reasoning.thinking == "high"
        assert loaded.web_search.backend == "zai"
        assert loaded.web_fetch.jina_api_key == "jk"

    def test_save_global_config_creates_directory(self, monkeypatch, tmp_path):
        monkeypatch.setattr("anappt.llm.provider.Path.home", lambda: tmp_path)

        config = ModelsConfig()
        saved_path = save_global_config(config)
        assert saved_path.parent.exists()
