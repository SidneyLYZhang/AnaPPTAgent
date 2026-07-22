"""Configuration model definitions for AnaPPTAgent.

Defines Pydantic models for report configuration and LLM model configuration,
with YAML serialization and environment variable expansion support.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


def _expand_env_vars(value: Any) -> Any:
    """Expand ${VAR} syntax in string values using environment variables.

    If the environment variable is not set, the original ${VAR} text is kept.

    Args:
        value: Any value; strings are processed, others are returned as-is.

    Returns:
        Value with environment variables expanded in strings.
    """
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([^}]+)\}")

        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        return pattern.sub(replacer, value)
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def _mask_secret(value: str | None) -> str:
    """Mask a secret value for safe display.

    - ``None`` or empty string → ``<unset>``
    - Unexpanded ``${VAR}`` literal (contains ``${`` and ends with ``}``) →
      returned as-is so the user can see which variable is referenced.
    - Actual value with length >= 8 → ``****`` plus the last 4 characters.
    - Actual value with length < 8 (and non-empty) → ``****``.

    Args:
        value: The secret string to mask (or None).

    Returns:
        Masked representation safe to print.
    """
    if not value:
        return "<unset>"
    if "${" in value and value.endswith("}"):
        return value  # Unexpanded ${VAR} literal — display as-is.
    if len(value) >= 8:
        return "****" + value[-4:]
    return "****"


def _web_source(
    env_val: str | None, yaml_val: str | None
) -> tuple[str | None, str | None]:
    """Resolve a web config field's effective value and its source tag.

    Environment variables take precedence over yaml. Returns a
    ``(display_value, source_tag)`` tuple where ``source_tag`` is one of
    ``"env"``, ``"yaml"`` or ``None`` (when neither source provides a value).

    Args:
        env_val: Value read from the environment variable (or None).
        yaml_val: Value read from the yaml ModelsConfig (or None).

    Returns:
        Tuple of (effective value or None, source tag or None).
    """
    if env_val:
        return env_val, "env"
    if yaml_val:
        return yaml_val, "yaml"
    return None, None


def _format_thinking(thinking: str | int | bool | None) -> str:
    """Format the ``thinking`` field of a ModelRoleConfig for display.

    - ``None`` → ``<max>`` (use the model's maximum thinking effort).
    - ``False`` (bool) → ``FALSE`` (the canonical disable sentinel).
    - ``True`` (bool) → ``TRUE``.
    - Integers and other strings → their ``str()`` representation.

    Args:
        thinking: The thinking field value.

    Returns:
        Human-readable representation.
    """
    if thinking is None:
        return "<max>"
    if thinking is False:
        return "FALSE"
    if thinking is True:
        return "TRUE"
    return str(thinking)


class ProjectInfo(BaseModel):
    """Project metadata."""

    name: str = ""
    type: str = "one_time"  # one_time | monthly | quarterly
    created: str = ""


class ReportInfo(BaseModel):
    """Report topic and goals."""

    topic: str = ""
    motivation: str = ""
    audience: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class DeliveryInfo(BaseModel):
    """Delivery format and style preferences."""

    ppt_pages: str = "15-20"
    formats: list[str] = Field(default_factory=lambda: ["pptx", "html"])
    theme_preference: str | None = None


class ReportConfig(BaseModel):
    """Top-level report configuration loaded from report.yaml."""

    project: ProjectInfo = Field(default_factory=ProjectInfo)
    report: ReportInfo = Field(default_factory=ReportInfo)
    delivery: DeliveryInfo = Field(default_factory=DeliveryInfo)

    @classmethod
    def from_yaml(cls, path: str | Path) -> ReportConfig:
        """Load configuration from a YAML file with env var expansion.

        Args:
            path: Path to the YAML file.

        Returns:
            Parsed ReportConfig with environment variables expanded.
        """
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        expanded = _expand_env_vars(raw)
        return cls.model_validate(expanded)

    def to_yaml(self) -> str:
        """Serialize configuration to YAML string.

        Returns:
            YAML-formatted string of the configuration.
        """
        data = self.model_dump()
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


class ModelRoleConfig(BaseModel):
    """Configuration for a single LLM model role.

    The optional ``thinking`` field controls reasoning effort when calling
    the LLM:

    - ``None`` (default) → use the model's maximum thinking effort.
    - String ``FALSE``/``OFF`` (case-insensitive) or boolean ``False`` →
      explicitly disable thinking.
    - Other strings (e.g. ``low``/``medium``/``high``) or integers (used as
      ``budget_tokens``) → explicit thinking strength.
    """

    provider: str = ""
    model: str = ""
    api_base: str | None = None
    api_key: str | None = None
    thinking: str | int | bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRoleConfig:
        """Create from a dictionary with env var expansion."""
        expanded = _expand_env_vars(data)
        return cls.model_validate(expanded)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return self.model_dump(exclude_none=True)


class WebSearchConfig(BaseModel):
    """Configuration for web search backends."""

    backend: str | None = None  # duckduckgo | anysearch | zai
    anysearch_api_key: str | None = None
    zai_api_key: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WebSearchConfig:
        """Create from a dictionary with env var expansion."""
        expanded = _expand_env_vars(data)
        return cls.model_validate(expanded)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return self.model_dump(exclude_none=True)


class WebFetchConfig(BaseModel):
    """Configuration for web fetch (Jina Reader)."""

    jina_api_key: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WebFetchConfig:
        """Create from a dictionary with env var expansion."""
        expanded = _expand_env_vars(data)
        return cls.model_validate(expanded)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return self.model_dump(exclude_none=True)


class ModelsConfig(BaseModel):
    """Configuration for all three LLM model roles and web capabilities."""

    reasoning: ModelRoleConfig = Field(default_factory=ModelRoleConfig)
    analysis: ModelRoleConfig = Field(default_factory=ModelRoleConfig)
    writing: ModelRoleConfig = Field(default_factory=ModelRoleConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    web_fetch: WebFetchConfig = Field(default_factory=WebFetchConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> ModelsConfig:
        """Load model configuration from a YAML file with env var expansion.

        Args:
            path: Path to the YAML file.

        Returns:
            Parsed ModelsConfig with environment variables expanded.
        """
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        expanded = _expand_env_vars(raw)
        return cls.model_validate(expanded)

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        data = self.model_dump(exclude_none=True)
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def to_effective_yaml(self) -> str:
        """Render the effective configuration as a human-readable string.

        The output reflects the merged effective config (env > yaml > default).
        Sensitive fields (``api_key``, ``anysearch_api_key``, ``zai_api_key``,
        ``jina_api_key``) are masked via :func:`_mask_secret`. Web section
        fields are annotated inline with their source (``(env)`` / ``(yaml)``
        / ``(default)``). LLM role fields are not annotated because
        ``${VAR}`` expansion makes the source ambiguous after load.

        The output is YAML-styled but not strictly parseable by
        :meth:`from_yaml` (due to masking and source tags).

        Returns:
            Multi-line string of the effective configuration.
        """
        lines: list[str] = [
            "# AnaPPTAgent 有效配置 (env > yaml > default)",
            "",
        ]

        # LLM role sections — no source tags (env-var expansion makes the
        # source ambiguous after load).
        for role_name in ("reasoning", "analysis", "writing"):
            role: ModelRoleConfig = getattr(self, role_name)
            lines.append(f"{role_name}:")
            lines.append(f"  provider: {role.provider or '<unset>'}")
            lines.append(f"  model: {role.model or '<unset>'}")
            lines.append(f"  api_base: {role.api_base or '<unset>'}")
            lines.append(f"  api_key: {_mask_secret(role.api_key)}")
            lines.append(f"  thinking: {_format_thinking(role.thinking)}")
            lines.append("")

        # web_search section — annotate each field with its source.
        lines.append("web_search:")
        ws_backend_val, ws_backend_src = _web_source(
            os.environ.get("WEB_SEARCH_BACKEND"),
            self.web_search.backend,
        )
        if ws_backend_val:
            lines.append(f"  backend: {ws_backend_val} ({ws_backend_src})")
        else:
            lines.append("  backend: auto (default)")

        any_val, any_src = _web_source(
            os.environ.get("ANYSEARCH_API_KEY"),
            self.web_search.anysearch_api_key,
        )
        if any_val:
            lines.append(
                f"  anysearch_api_key: {_mask_secret(any_val)} ({any_src})"
            )
        else:
            lines.append("  anysearch_api_key: <unset>")

        zai_val, zai_src = _web_source(
            os.environ.get("ZAI_API_KEY"),
            self.web_search.zai_api_key,
        )
        if zai_val:
            lines.append(f"  zai_api_key: {_mask_secret(zai_val)} ({zai_src})")
        else:
            lines.append("  zai_api_key: <unset>")
        lines.append("")

        # web_fetch section — annotate jina_api_key source.
        lines.append("web_fetch:")
        jina_val, jina_src = _web_source(
            os.environ.get("JINA_API_KEY"),
            self.web_fetch.jina_api_key,
        )
        if jina_val:
            lines.append(
                f"  jina_api_key: {_mask_secret(jina_val)} ({jina_src})"
            )
        else:
            lines.append("  jina_api_key: <unset>")

        return "\n".join(lines)
