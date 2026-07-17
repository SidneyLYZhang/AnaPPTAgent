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
        params.update(kwargs)
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


def merge_config(global_config: ModelsConfig, project_config: ModelsConfig | None) -> ModelsConfig:
    """Merge project-level config over global config.

    Project-level settings override global settings for each role.
    Only non-empty fields in the project config override the global config.

    Args:
        global_config: The global configuration.
        project_config: The project-level configuration (may be None).

    Returns:
        Merged ModelsConfig.
    """
    if project_config is None:
        return global_config

    def merge_role(
        global_role: ModelRoleConfig, project_role: ModelRoleConfig
    ) -> ModelRoleConfig:
        """Merge a single role config, project overrides global."""
        return ModelRoleConfig(
            provider=project_role.provider if project_role.provider else global_role.provider,
            model=project_role.model if project_role.model else global_role.model,
            api_base=project_role.api_base if project_role.api_base else global_role.api_base,
            api_key=project_role.api_key if project_role.api_key else global_role.api_key,
        )

    return ModelsConfig(
        reasoning=merge_role(global_config.reasoning, project_config.reasoning),
        analysis=merge_role(global_config.analysis, project_config.analysis),
        writing=merge_role(global_config.writing, project_config.writing),
    )


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
