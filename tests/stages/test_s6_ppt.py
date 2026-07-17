"""Tests for S6PPTStage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.config import DeliveryInfo, ReportConfig
from anappt.io.state import StateManager
from anappt.stages.s6_ppt import S6PPTStage
from anappt.types import PipelineContext


@pytest.fixture
def config() -> ReportConfig:
    """Return a ReportConfig with delivery settings."""
    return ReportConfig(
        delivery=DeliveryInfo(
            ppt_pages="15-20",
            formats=["pptx", "html"],
            theme_preference="default",
        ),
    )


@pytest.fixture
def ctx(tmp_path: Path, config: ReportConfig) -> PipelineContext:
    """Return a PipelineContext with S5 report output."""
    llm = MagicMock()
    state = StateManager(tmp_path / ".anappt" / "state.yaml")

    ctx = PipelineContext(
        project_dir=tmp_path,
        config=config,
        llm=llm,
        state=state,
    )

    # Create S5 report output
    report_path = ctx.get_artifact_path("report.md")
    report_path.write_text(
        "# Executive Summary\n\nKey findings.\n\n## Details\n\n- Point 1\n- Point 2",
        encoding="utf-8",
    )

    return ctx


class TestS6Attributes:
    """Tests for stage attributes."""

    def test_stage_id(self) -> None:
        assert S6PPTStage().stage_id == "S6"

    def test_stage_name(self) -> None:
        assert S6PPTStage().stage_name == "stage.s6.name"

    def test_model_role(self) -> None:
        assert S6PPTStage().model_role == "writing"


class TestS6Run:
    """Tests for the run method."""

    def test_successful_run(self, ctx: PipelineContext) -> None:
        stage = S6PPTStage()
        output = stage.run(ctx)

        assert output.success is True
        assert len(output.artifacts) >= 1
        assert "presentation.html" in output.artifacts[0]

    def test_generates_html_file(self, ctx: PipelineContext) -> None:
        stage = S6PPTStage()
        stage.run(ctx)

        ppt_path = ctx.get_artifact_path("ppt") / "presentation.html"
        assert ppt_path.exists()
        content = ppt_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Executive Summary" in content

    def test_missing_report(self, ctx: PipelineContext) -> None:
        ctx.get_artifact_path("report.md").unlink()

        stage = S6PPTStage()
        output = stage.run(ctx)

        assert output.success is False
        assert "Report not found" in output.summary

    def test_uses_config_theme(self, ctx: PipelineContext) -> None:
        stage = S6PPTStage()
        output = stage.run(ctx)

        assert output.data["theme"] == "default"

    def test_no_theme_preference_uses_default(
        self, tmp_path: Path
    ) -> None:
        """When no theme in config and no UI, should use default."""
        config = ReportConfig(
            delivery=DeliveryInfo(theme_preference=None),
        )
        llm = MagicMock()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=config,
            llm=llm,
            state=state,
        )
        ctx.get_artifact_path("report.md").write_text("# Title\n\nContent", encoding="utf-8")

        stage = S6PPTStage()
        output = stage.run(ctx)

        assert output.success is True
        assert output.data["theme"] == "default"

    def test_get_artifacts(self, ctx: PipelineContext) -> None:
        stage = S6PPTStage()
        artifacts = stage.get_artifacts(ctx)
        assert "output/ppt/presentation.html" in artifacts

    def test_ppt_path_in_data(self, ctx: PipelineContext) -> None:
        stage = S6PPTStage()
        output = stage.run(ctx)

        assert "ppt_path" in output.data
        assert output.data["ppt_path"].endswith("presentation.html")

    def test_invalid_markdown_fails(self, ctx: PipelineContext) -> None:
        """Report with no headings should fail."""
        report_path = ctx.get_artifact_path("report.md")
        report_path.write_text("Just plain text no headings", encoding="utf-8")

        stage = S6PPTStage()
        output = stage.run(ctx)

        assert output.success is False


class TestS6Prerequisites:
    """Tests for validate_prerequisites."""

    def test_requires_s5_completed(self, tmp_path: Path) -> None:
        from anappt.io.state import StageStatus

        state = StateManager(tmp_path / "state.yaml")
        stage = S6PPTStage()

        assert stage.validate_prerequisites(state) is False

        for sid in ["S1", "S2", "S3", "S4", "S5"]:
            state.transition(sid, StageStatus.IN_PROGRESS)
            state.transition(sid, StageStatus.AWAITING_REVIEW)
            state.transition(sid, StageStatus.COMPLETED)

        assert stage.validate_prerequisites(state) is True
