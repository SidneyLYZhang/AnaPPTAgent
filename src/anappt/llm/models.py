"""Model role and type definitions for AnaPPTAgent LLM layer."""

from __future__ import annotations

from typing import Literal

# Three model roles corresponding to pipeline stages
ModelRole = Literal["reasoning", "analysis", "writing"]

# Mapping from role to ModelsConfig field name
ROLE_TO_FIELD: dict[str, str] = {
    "reasoning": "reasoning",
    "analysis": "analysis",
    "writing": "writing",
}
