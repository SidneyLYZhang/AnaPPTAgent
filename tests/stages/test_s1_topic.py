"""Tests for S1TopicStage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.config import ReportConfig
from anappt.io.state import StateManager
from anappt.stages.s1_topic import S1TopicStage
from anappt.types import PipelineContext


@pytest.fixture
def config() -> ReportConfig:
    """Return a ReportConfig with test data."""
    from anappt.io.config import DeliveryInfo, ProjectInfo, ReportInfo

    return ReportConfig(
        project=ProjectInfo(name="Test Project", type="one_time"),
        report=ReportInfo(
            topic="Sales Analysis Q1 2025",
            motivation="Understand Q1 sales trends",
            audience=["Management"],
            objectives=["Identify top products", "Analyze revenue trends"],
            success_criteria=["Clear actionable insights"],
        ),
        delivery=DeliveryInfo(),
    )


@pytest.fixture
def ctx(
    tmp_path: Path,
    config: ReportConfig,
) -> PipelineContext:
    """Return a PipelineContext with mock LLM."""
    llm = MagicMock()
    llm.chat.return_value = "# Refined Topic\n\nThis is the refined topic document."
    state = StateManager(tmp_path / ".anappt" / "state.yaml")
    return PipelineContext(
        project_dir=tmp_path,
        config=config,
        llm=llm,
        state=state,
    )


class TestS1Attributes:
    """Tests for stage attributes."""

    def test_stage_id(self) -> None:
        assert S1TopicStage().stage_id == "S1"

    def test_stage_name(self) -> None:
        assert S1TopicStage().stage_name == "stage.s1.name"

    def test_model_role(self) -> None:
        assert S1TopicStage().model_role == "reasoning"


class TestS1Run:
    """Tests for the run method."""

    def test_successful_run(self, ctx: PipelineContext) -> None:
        stage = S1TopicStage()
        output = stage.run(ctx)

        assert output.success is True
        assert len(output.artifacts) == 1
        assert "s1_topic.md" in output.artifacts[0]
        assert output.next_action == "confirm"

    def test_writes_artifact_file(self, ctx: PipelineContext) -> None:
        stage = S1TopicStage()
        stage.run(ctx)

        artifact_path = ctx.get_anappt_path("s1_topic.md")
        assert artifact_path.exists()
        content = artifact_path.read_text(encoding="utf-8")
        assert "Refined Topic" in content

    def test_llm_called_with_reasoning_role(self, ctx: PipelineContext) -> None:
        stage = S1TopicStage()
        stage.run(ctx)

        ctx.llm.chat.assert_called_once()
        call_args = ctx.llm.chat.call_args
        role = call_args[0][0] if call_args[0] else call_args.kwargs.get("role")
        assert role == "reasoning"

    def test_llm_failure(self, ctx: PipelineContext) -> None:
        ctx.llm.chat.side_effect = Exception("API error")
        stage = S1TopicStage()
        output = stage.run(ctx)

        assert output.success is False
        assert "LLM call failed" in output.summary
        assert output.next_action == "retry"

    def test_get_artifacts(self, ctx: PipelineContext) -> None:
        stage = S1TopicStage()
        artifacts = stage.get_artifacts(ctx)
        assert ".anappt/s1_topic.md" in artifacts

    def test_summary_truncated(self, ctx: PipelineContext) -> None:
        long_response = "A" * 300
        ctx.llm.chat.return_value = long_response
        stage = S1TopicStage()
        output = stage.run(ctx)
        assert len(output.summary) <= 203  # 200 + "..."


class TestS1Prerequisites:
    """Tests for validate_prerequisites."""

    def test_s1_no_prerequisites(self, tmp_path: Path) -> None:
        state = StateManager(tmp_path / "state.yaml")
        stage = S1TopicStage()
        assert stage.validate_prerequisites(state) is True
