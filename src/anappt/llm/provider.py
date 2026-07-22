"""LLM provider layer for AnaPPTAgent.

Wraps litellm with role-based model selection and provides global
configuration management.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import litellm

from anappt.io.config import ModelRoleConfig, ModelsConfig
from anappt.llm.models import ModelRole


class AnaPPTLLM:
    """Thin wrapper around litellm with role-based model selection.

    Supports three model roles: reasoning (S1-S2), analysis (S4),
    and writing (S5-S6). Each role can use a different model.
    """

    def __init__(self, config: ModelsConfig) -> None:
        """Initialize with model configuration.

        Args:
            config: ModelsConfig containing all three role configurations.
        """
        self.config = config
        self._models: dict[str, ModelRoleConfig] = {
            "reasoning": config.reasoning,
            "analysis": config.analysis,
            "writing": config.writing,
        }

    def _model_for_role(self, role: ModelRole) -> ModelRoleConfig:
        """Get the ModelRoleConfig for a given role.

        Args:
            role: One of 'reasoning', 'analysis', 'writing'.

        Returns:
            ModelRoleConfig for the specified role.

        Raises:
            ValueError: If the role is invalid.
        """
        if role not in self._models:
            valid = list(self._models.keys())
            raise ValueError(f"Invalid model role: {role}. Must be one of: {valid}")
        return self._models[role]

    def _build_litellm_params(
        self, role_config: ModelRoleConfig, **kwargs: Any
    ) -> dict[str, Any]:
        """Build parameters for litellm.completion() call.

        Args:
            role_config: The model configuration for this role.
            **kwargs: Additional parameters to pass through.

        Returns:
            Dictionary of parameters for litellm.completion().
        """
        params: dict[str, Any] = {
            "model": role_config.model,
        }
        if role_config.api_key:
            params["api_key"] = role_config.api_key
        if role_config.api_base:
            params["api_base"] = role_config.api_base
        # Apply thinking params from config (caller kwargs take precedence)
        thinking_params = _map_thinking_to_params(role_config.provider, role_config.thinking)
        params.update(thinking_params)
        params.update(kwargs)  # caller-supplied kwargs override thinking params
        return params

    def chat(self, role: ModelRole, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Send a chat completion request using the model for the given role.

        Synchronously calls litellm.completion().

        Args:
            role: Model role to use.
            messages: List of message dicts (role/content format).
            **kwargs: Additional parameters for litellm.

        Returns:
            The text content of the response.

        Raises:
            ValueError: If the role is invalid.
            Exception: If the litellm call fails.
        """
        role_config = self._model_for_role(role)
        params = self._build_litellm_params(role_config, **kwargs)
        response = litellm.completion(messages=messages, **params)
        return response.choices[0].message.content or ""

    def chat_with_tools(
        self,
        role: ModelRole,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a chat completion request with tool/function calling support.

        Args:
            role: Model role to use.
            messages: List of message dicts.
            tools: List of tool schemas in litellm/OpenAI function calling format.
            **kwargs: Additional parameters for litellm.

        Returns:
            Dictionary with:
                - 'content': Text content (may be empty if tool_calls present)
                - 'tool_calls': List of tool call dicts (may be empty)
                - 'raw_response': The raw litellm response object
        """
        role_config = self._model_for_role(role)
        params = self._build_litellm_params(role_config, tools=tools, **kwargs)
        response = litellm.completion(messages=messages, **params)
        message = response.choices[0].message

        result: dict[str, Any] = {
            "content": message.content or "",
            "tool_calls": [],
            "raw_response": response,
        }

        # Parse tool calls if present
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                result["tool_calls"].append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                )

        return result


def _map_thinking_to_params(provider: str, thinking: str | int | bool | None) -> dict[str, Any]:
    """Map the ``thinking`` config field to LiteLLM provider-specific params.

    Semantics:
    - None (default): for known providers that default to non-max thinking
      (e.g. OpenAI o-series defaults to ``medium``), proactively pass the
      "max" param (``reasoning_effort="high"``). For other providers, pass
      nothing so the model uses its default (which is already max).
    - String ``FALSE``/``OFF`` (case-insensitive) or bool False: pass the
      provider's "disable thinking" param. OpenAI: ``reasoning_effort="minimal"``.
      Anthropic: pass nothing (omit ``thinking``). Unknown providers: pass nothing.
    - String ``low``/``medium``/``high``: OpenAI ``reasoning_effort=<value>``.
      Other providers: pass nothing (unsupported, silently skipped).
    - Integer N: Anthropic ``thinking={"type": "enabled", "budget_tokens": N}``.
      Other providers: pass nothing (silently skipped).

    Args:
        provider: The provider string from ModelRoleConfig.provider.
        thinking: The thinking config value.

    Returns:
        Dict of extra params to merge into litellm.completion() kwargs.
    """
    provider_lower = (provider or "").lower()
    is_openai = "openai" in provider_lower or provider_lower == ""
    is_anthropic = "anthropic" in provider_lower or "claude" in provider_lower

    # Case 1: None (default) - proactively use max for OpenAI o-series
    if thinking is None:
        if is_openai:
            return {"reasoning_effort": "high"}
        return {}

    # Case 2: Disabled (FALSE/OFF string case-insensitive, or bool False)
    is_disabled = thinking is False or (
        isinstance(thinking, str) and thinking.strip().upper() in ("FALSE", "OFF")
    )
    if is_disabled:
        if is_openai:
            return {"reasoning_effort": "minimal"}
        # Anthropic & unknown providers: pass nothing (omit thinking)
        return {}

    # Case 3: Explicit strength string (low/medium/high)
    if isinstance(thinking, str) and thinking.strip().lower() in ("low", "medium", "high"):
        if is_openai:
            return {"reasoning_effort": thinking.strip().lower()}
        # Other providers: silently skipped
        return {}

    # Case 4: Integer N (budget_tokens) - only Anthropic
    if isinstance(thinking, int) and not isinstance(thinking, bool):
        if is_anthropic:
            return {"thinking": {"type": "enabled", "budget_tokens": thinking}}
        # Other providers: silently skipped
        return {}

    # Anything else (bool True, unknown strings, etc.): silently skip
    return {}


# --- Global Configuration Management ---


def _get_global_config_path() -> Path:
    """Return the path to the global model config file.

    Returns:
        Path to ~/.anappt/models.yaml
    """
    return Path.home() / ".anappt" / "models.yaml"


def load_global_config() -> ModelsConfig:
    """Load global model configuration from ~/.anappt/models.yaml.

    If the file does not exist, returns a default empty ModelsConfig.

    Returns:
        ModelsConfig loaded from the global config file.
    """
    config_path = _get_global_config_path()
    if not config_path.exists():
        return ModelsConfig()
    return ModelsConfig.from_yaml(config_path)


def save_global_config(config: ModelsConfig) -> Path:
    """Save global model configuration to ~/.anappt/models.yaml.

    Creates the directory if it does not exist.

    Args:
        config: The configuration to save.

    Returns:
        Path to the saved file.
    """
    config_path = _get_global_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_str = config.to_yaml()
    config_path.write_text(yaml_str, encoding="utf-8")
    return config_path
