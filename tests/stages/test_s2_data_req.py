"""Tests for S2DataRequirementStage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.config import ReportConfig
from anappt.io.state import StateManager
from anappt.stages.s2_data_req import S2DataRequirementStage
from anappt.types import PipelineContext


@pytest.fixture
def config() -> ReportConfig:
    """Return a test ReportConfig."""
    return ReportConfig()


@pytest.fixture
def ctx(tmp_path: Path, config: ReportConfig) -> PipelineContext:
    """Return a PipelineContext with mock LLM and S1 output."""
    llm = MagicMock()
    llm.chat.return_value = "# Data Requirements\n\nRequired data tables:\n- Sales\n- Customers"
    state = StateManager(tmp_path / ".anappt" / "state.yaml")

    ctx = PipelineContext(
        project_dir=tmp_path,
        config=config,
        llm=llm,
        state=state,
    )

    # Create S1 output
    s1_path = ctx.get_anappt_path("s1_topic.md")
    s1_path.write_text("# S1 Topic\n\nRefined topic here.", encoding="utf-8")

    # Create data directory with a sample file
    data_dir = ctx.get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "sample.csv").write_text("name,value\nA,1\n", encoding="utf-8")

    return ctx


class TestS2Attributes:
    """Tests for stage attributes."""

    def test_stage_id(self) -> None:
        assert S2DataRequirementStage().stage_id == "S2"

    def test_stage_name(self) -> None:
        assert S2DataRequirementStage().stage_name == "stage.s2.name"

    def test_model_role(self) -> None:
        assert S2DataRequirementStage().model_role == "reasoning"


class TestS2Run:
    """Tests for the run method."""

    def test_successful_run(self, ctx: PipelineContext) -> None:
        stage = S2DataRequirementStage()
        output = stage.run(ctx)

        assert output.success is True
        assert len(output.artifacts) == 1
        assert "s2_data_requirement.md" in output.artifacts[0]

    def test_writes_artifact(self, ctx: PipelineContext) -> None:
        stage = S2DataRequirementStage()
        stage.run(ctx)

        artifact_path = ctx.get_anappt_path("s2_data_requirement.md")
        assert artifact_path.exists()
        content = artifact_path.read_text(encoding="utf-8")
        assert "Data Requirements" in content

    def test_llm_called_with_reasoning_role(self, ctx: PipelineContext) -> None:
        stage = S2DataRequirementStage()
        stage.run(ctx)

        ctx.llm.chat.assert_called_once()
        call_args = ctx.llm.chat.call_args
        role = call_args[0][0] if call_args[0] else call_args.kwargs.get("role")
        assert role == "reasoning"

    def test_missing_s1_output(self, ctx: PipelineContext) -> None:
        # Remove S1 output
        ctx.get_anappt_path("s1_topic.md").unlink()

        stage = S2DataRequirementStage()
        output = stage.run(ctx)

        assert output.success is False
        assert "S1 output not found" in output.summary

    def test_llm_failure(self, ctx: PipelineContext) -> None:
        ctx.llm.chat.side_effect = Exception("Network error")
        stage = S2DataRequirementStage()
        output = stage.run(ctx)

        assert output.success is False
        assert "LLM call failed" in output.summary

    def test_data_files_in_context(self, ctx: PipelineContext) -> None:
        stage = S2DataRequirementStage()
        output = stage.run(ctx)

        # The existing data files should be in the output data
        assert "existing_files" in output.data
        assert "sample.csv" in output.data["existing_files"]

    def test_get_artifacts(self, ctx: PipelineContext) -> None:
        stage = S2DataRequirementStage()
        artifacts = stage.get_artifacts(ctx)
        assert ".anappt/s2_data_requirement.md" in artifacts


class TestS2Prerequisites:
    """Tests for validate_prerequisites."""

    def test_requires_s1_completed(self, tmp_path: Path) -> None:
        from anappt.io.state import StageStatus

        state = StateManager(tmp_path / "state.yaml")
        stage = S2DataRequirementStage()

        # S1 not completed
        assert stage.validate_prerequisites(state) is False

        # Complete S1
        state.transition("S1", StageStatus.IN_PROGRESS)
        state.transition("S1", StageStatus.AWAITING_REVIEW)
        state.transition("S1", StageStatus.COMPLETED)
        assert stage.validate_prerequisites(state) is True
