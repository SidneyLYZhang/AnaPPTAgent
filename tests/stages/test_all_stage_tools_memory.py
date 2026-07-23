"""Centralized test: every stage's tools() subset includes update_memory.

The conversation runner registers an ``update_memory`` tool that lets the
LLM append a dated entry to ``.anappt/memory.md`` mid-conversation. Every
stage (S1-S6) must expose this tool in its ``tools(ctx)`` subset so the
LLM can record milestones as they happen.

Rather than scattering one assert per stage-test file, this module
parametrizes over :func:`build_stage_registry` so the coverage stays in
sync with the registered stages automatically.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.config import ReportConfig
from anappt.io.state import StateManager
from anappt.stages import build_stage_registry
from anappt.types import PipelineContext

# Stage ids derived from the canonical registry at collection time so the
# parametrization tracks the registered stages without manual maintenance.
_STAGE_IDS = list(build_stage_registry().keys())


def _make_ctx(tmp_path: Path) -> PipelineContext:
    """Build a minimal PipelineContext sufficient for ``stage.tools(ctx)``."""
    return PipelineContext(
        project_dir=tmp_path,
        config=ReportConfig(),
        llm=MagicMock(),
        state=StateManager(tmp_path / ".anappt" / "state.yaml"),
    )


@pytest.mark.parametrize("stage_id", _STAGE_IDS)
def test_stage_tools_include_update_memory(stage_id: str, tmp_path: Path) -> None:
    """Every registered stage must expose ``update_memory`` in its tools()."""
    registry = build_stage_registry()
    stage = registry[stage_id]
    ctx = _make_ctx(tmp_path)
    assert "update_memory" in stage.tools(ctx)
