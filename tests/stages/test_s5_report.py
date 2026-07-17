"""Tests for S5ReportStage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.config import ReportConfig
from anappt.io.state import StateManager
from anappt.stages.s5_report import S5ReportStage
from anappt.types import PipelineContext


@pytest.fixture
def config() -> ReportConfig:
    """Return a test ReportConfig."""
    return ReportConfig()


@pytest.fixture
def ctx(tmp_path: Path, config: ReportConfig) -> PipelineContext:
    """Return a PipelineContext with S4 output."""
    llm = MagicMock()
    llm.chat.return_value = "# Analysis Report\n\n## Executive Summary\n\nKey findings here."
    state = StateManager(tmp_path / ".anappt" / "state.yaml")

    ctx = PipelineContext(
        project_dir=tmp_path,
        config=config,
        llm=llm,
        state=state,
    )

    # Create S4 output
    ctx.get_anappt_path("s4_analysis_report.md").write_text(
        "# Raw Analysis\n\nData analysis results.", encoding="utf-8"
    )

    # Create S1 output for context
    ctx.get_anappt_path("s1_topic.md").write_text("# Topic\n\nSales analysis", encoding="utf-8")

    return ctx


class TestS5Attributes:
    """Tests for stage attributes."""

    def test_stage_id(self) -> None:
        assert S5ReportStage().stage_id == "S5"

    def test_stage_name(self) -> None:
        assert S5ReportStage().stage_name == "stage.s5.name"

    def test_model_role(self) -> None:
        assert S5ReportStage().model_role == "writing"


class TestS5Run:
    """Tests for the run method."""

    def test_successful_run(self, ctx: PipelineContext) -> None:
        stage = S5ReportStage()
        output = stage.run(ctx)

        assert output.success is True
        assert len(output.artifacts) >= 1

    def test_writes_report_to_output(self, ctx: PipelineContext) -> None:
        stage = S5ReportStage()
        stage.run(ctx)

        report_path = ctx.get_artifact_path("report.md")
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "Executive Summary" in content

    def test_writes_copy_to_anappt(self, ctx: PipelineContext) -> None:
        stage = S5ReportStage()
        stage.run(ctx)

        anappt_copy = ctx.get_anappt_path("s5_report.md")
        assert anappt_copy.exists()

    def test_llm_called_with_writing_role(self, ctx: PipelineContext) -> None:
        stage = S5ReportStage()
        stage.run(ctx)

        ctx.llm.chat.assert_called_once()
        call_args = ctx.llm.chat.call_args
        role = call_args[0][0] if call_args[0] else call_args.kwargs.get("role")
        assert role == "writing"

    def test_missing_s4_output(self, ctx: PipelineContext) -> None:
        ctx.get_anappt_path("s4_analysis_report.md").unlink()

        stage = S5ReportStage()
        output = stage.run(ctx)

        assert output.success is False
        assert "S4 analysis report not found" in output.summary

    def test_llm_failure(self, ctx: PipelineContext) -> None:
        ctx.llm.chat.side_effect = Exception("API timeout")

        stage = S5ReportStage()
        output = stage.run(ctx)

        assert output.success is False
        assert "LLM call failed" in output.summary

    def test_get_artifacts(self, ctx: PipelineContext) -> None:
        stage = S5ReportStage()
        artifacts = stage.get_artifacts(ctx)
        assert "output/report.md" in artifacts
        assert ".anappt/s5_report.md" in artifacts

    def test_report_path_in_data(self, ctx: PipelineContext) -> None:
        stage = S5ReportStage()
        output = stage.run(ctx)

        assert "report_path" in output.data
        assert output.data["report_path"].endswith("report.md")


class TestS5Prerequisites:
    """Tests for validate_prerequisites."""

    def test_requires_s4_completed(self, tmp_path: Path) -> None:
        from anappt.io.state import StageStatus

        state = StateManager(tmp_path / "state.yaml")
        stage = S5ReportStage()

        assert stage.validate_prerequisites(state) is False

        for sid in ["S1", "S2", "S3", "S4"]:
            state.transition(sid, StageStatus.IN_PROGRESS)
            state.transition(sid, StageStatus.AWAITING_REVIEW)
            state.transition(sid, StageStatus.COMPLETED)

        assert stage.validate_prerequisites(state) is True
