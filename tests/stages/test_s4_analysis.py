"""Tests for S4AnalysisStage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.config import ReportConfig
from anappt.io.state import StateManager
from anappt.stages.s4_analysis import S4AnalysisStage
from anappt.types import PipelineContext


@pytest.fixture
def config() -> ReportConfig:
    """Return a test ReportConfig."""
    return ReportConfig()


@pytest.fixture
def ctx(tmp_path: Path, config: ReportConfig) -> PipelineContext:
    """Return a PipelineContext with mock LLM and prior stage outputs."""
    llm = MagicMock()
    llm.chat.return_value = "# Analysis Report\n\nKey findings: revenue up 20%"
    llm.chat_with_tools.return_value = {
        "content": "Final analysis answer",
        "tool_calls": [],
    }
    state = StateManager(tmp_path / ".anappt" / "state.yaml")

    ctx = PipelineContext(
        project_dir=tmp_path,
        config=config,
        llm=llm,
        state=state,
    )

    # Create S1 and S2 outputs
    ctx.get_anappt_path("s1_topic.md").write_text("# Topic\n\nSales analysis", encoding="utf-8")
    ctx.get_anappt_path("s2_data_requirement.md").write_text(
        "# Data Requirements\n\nNeed sales data", encoding="utf-8"
    )

    # Create data directory with sample CSV
    data_dir = ctx.get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "sales.csv").write_text("product,revenue\nA,100\nB,200\n", encoding="utf-8")

    return ctx


class TestS4Attributes:
    """Tests for stage attributes."""

    def test_stage_id(self) -> None:
        assert S4AnalysisStage().stage_id == "S4"

    def test_stage_name(self) -> None:
        assert S4AnalysisStage().stage_name == "stage.s4.name"

    def test_model_role(self) -> None:
        assert S4AnalysisStage().model_role == "analysis"


class TestS4Run:
    """Tests for the run method."""

    def test_successful_run(self, ctx: PipelineContext) -> None:
        stage = S4AnalysisStage()
        output = stage.run(ctx)

        assert output.success is True
        assert len(output.artifacts) >= 1
        assert "s4_analysis_report.md" in output.artifacts[0]

    def test_writes_artifact(self, ctx: PipelineContext) -> None:
        stage = S4AnalysisStage()
        stage.run(ctx)

        artifact_path = ctx.get_anappt_path("s4_analysis_report.md")
        assert artifact_path.exists()

    def test_writes_data_info(self, ctx: PipelineContext) -> None:
        stage = S4AnalysisStage()
        stage.run(ctx)

        data_info_path = ctx.get_anappt_path("data_info.json")
        assert data_info_path.exists()

    def test_get_artifacts(self, ctx: PipelineContext) -> None:
        stage = S4AnalysisStage()
        artifacts = stage.get_artifacts(ctx)
        assert ".anappt/s4_analysis_report.md" in artifacts

    def test_llm_failure(self, ctx: PipelineContext) -> None:
        ctx.llm.chat_with_tools.side_effect = Exception("API error")
        ctx.llm.chat.side_effect = Exception("API error")

        stage = S4AnalysisStage()
        output = stage.run(ctx)

        assert output.success is False
        assert "Analysis failed" in output.summary

    def test_no_prior_outputs(self, tmp_path: Path, config: ReportConfig) -> None:
        """S4 should still run even without S1/S2 outputs."""
        llm = MagicMock()
        llm.chat_with_tools.return_value = {"content": "Result", "tool_calls": []}
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=config,
            llm=llm,
            state=state,
        )
        # Don't create S1/S2 outputs or data

        stage = S4AnalysisStage()
        output = stage.run(ctx)
        # Should still succeed (just with empty context)
        assert output.success is True


class TestS4Prerequisites:
    """Tests for validate_prerequisites."""

    def test_requires_s3_completed(self, tmp_path: Path) -> None:
        from anappt.io.state import StageStatus

        state = StateManager(tmp_path / "state.yaml")
        stage = S4AnalysisStage()

        assert stage.validate_prerequisites(state) is False

        for sid in ["S1", "S2", "S3"]:
            state.transition(sid, StageStatus.IN_PROGRESS)
            state.transition(sid, StageStatus.AWAITING_REVIEW)
            state.transition(sid, StageStatus.COMPLETED)

        assert stage.validate_prerequisites(state) is True


class TestS4ToolBuilding:
    """Tests for tool building in S4."""

    def test_build_tools_includes_python(self, ctx: PipelineContext) -> None:
        stage = S4AnalysisStage()
        tools, tool_defs = stage._build_tools(ctx)

        assert "execute_python" in tools
        assert any(td.name == "execute_python" for td in tool_defs)

    def test_build_tools_includes_search(self, ctx: PipelineContext) -> None:
        stage = S4AnalysisStage()
        tools, tool_defs = stage._build_tools(ctx)

        assert "search_web" in tools
        assert any(td.name == "search_web" for td in tool_defs)

    def test_build_tools_fetch_optional(self, ctx: PipelineContext, monkeypatch) -> None:
        # When JINA_API_KEY is not set, fetch should not be included
        monkeypatch.delenv("JINA_API_KEY", raising=False)

        stage = S4AnalysisStage()
        tools, tool_defs = stage._build_tools(ctx)

        assert "fetch_url" not in tools
        assert not any(td.name == "fetch_url" for td in tool_defs)

    def test_build_tools_fetch_available(self, ctx: PipelineContext, monkeypatch) -> None:
        # When JINA_API_KEY is set, fetch should be included
        monkeypatch.setenv("JINA_API_KEY", "test_key")

        stage = S4AnalysisStage()
        tools, tool_defs = stage._build_tools(ctx)

        assert "fetch_url" in tools
        assert any(td.name == "fetch_url" for td in tool_defs)
