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
    """Configuration for a single LLM model role."""

    provider: str = ""
    model: str = ""
    api_base: str | None = None
    api_key: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRoleConfig:
        """Create from a dictionary with env var expansion."""
        expanded = _expand_env_vars(data)
        return cls.model_validate(expanded)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return self.model_dump(exclude_none=True)


class ModelsConfig(BaseModel):
    """Configuration for all three LLM model roles."""

    reasoning: ModelRoleConfig = Field(default_factory=ModelRoleConfig)
    analysis: ModelRoleConfig = Field(default_factory=ModelRoleConfig)
    writing: ModelRoleConfig = Field(default_factory=ModelRoleConfig)

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
