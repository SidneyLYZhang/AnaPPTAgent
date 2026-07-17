"""Tests for S3DataLoadStage."""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.config import ReportConfig
from anappt.io.state import StateManager
from anappt.stages.s3_data_load import S3DataLoadStage
from anappt.types import PipelineContext


@pytest.fixture
def config() -> ReportConfig:
    """Return a test ReportConfig."""
    return ReportConfig()


@pytest.fixture
def ctx_with_data(tmp_path: Path, config: ReportConfig) -> PipelineContext:
    """Return a PipelineContext with sample data files."""
    state = StateManager(tmp_path / ".anappt" / "state.yaml")
    ctx = PipelineContext(
        project_dir=tmp_path,
        config=config,
        llm=MagicMock(),
        state=state,
    )

    # Create data directory with CSV files
    data_dir = ctx.get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Sales CSV
    sales_path = data_dir / "sales.csv"
    with open(sales_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["product", "revenue", "date"])
        writer.writerow(["Widget", "1000", "2025-01-01"])
        writer.writerow(["Gadget", "2000", "2025-01-02"])

    # Users CSV
    users_path = data_dir / "users.csv"
    with open(users_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "age"])
        writer.writerow(["Alice", "30"])
        writer.writerow(["Bob", "25"])

    return ctx


@pytest.fixture
def ctx_no_data(tmp_path: Path, config: ReportConfig) -> PipelineContext:
    """Return a PipelineContext with no data files."""
    state = StateManager(tmp_path / ".anappt" / "state.yaml")
    ctx = PipelineContext(
        project_dir=tmp_path,
        config=config,
        llm=MagicMock(),
        state=state,
    )
    # Data dir exists but is empty
    ctx.get_data_dir().mkdir(parents=True, exist_ok=True)
    return ctx


class TestS3Attributes:
    """Tests for stage attributes."""

    def test_stage_id(self) -> None:
        assert S3DataLoadStage().stage_id == "S3"

    def test_stage_name(self) -> None:
        assert S3DataLoadStage().stage_name == "stage.s3.name"

    def test_model_role(self) -> None:
        assert S3DataLoadStage().model_role == "reasoning"


class TestS3Run:
    """Tests for the run method."""

    def test_successful_run_with_data(self, ctx_with_data: PipelineContext) -> None:
        stage = S3DataLoadStage()
        output = stage.run(ctx_with_data)

        assert output.success is True
        assert len(output.artifacts) == 1
        assert "s3_data_profile.md" in output.artifacts[0]
        assert output.data["file_count"] == 2

    def test_no_data_files(self, ctx_no_data: PipelineContext) -> None:
        stage = S3DataLoadStage()
        output = stage.run(ctx_no_data)

        assert output.success is False
        assert "No data files" in output.summary or "No data" in output.summary

    def test_writes_data_profile(self, ctx_with_data: PipelineContext) -> None:
        stage = S3DataLoadStage()
        stage.run(ctx_with_data)

        profile_path = ctx_with_data.get_anappt_path("s3_data_profile.md")
        assert profile_path.exists()
        content = profile_path.read_text(encoding="utf-8")
        assert "Data Profile" in content
        assert "sales" in content
        assert "users" in content

    def test_profile_has_shape_info(self, ctx_with_data: PipelineContext) -> None:
        stage = S3DataLoadStage()
        stage.run(ctx_with_data)

        profile_path = ctx_with_data.get_anappt_path("s3_data_profile.md")
        content = profile_path.read_text(encoding="utf-8")
        assert "Shape" in content
        assert "rows" in content

    def test_profile_has_columns(self, ctx_with_data: PipelineContext) -> None:
        stage = S3DataLoadStage()
        stage.run(ctx_with_data)

        profile_path = ctx_with_data.get_anappt_path("s3_data_profile.md")
        content = profile_path.read_text(encoding="utf-8")
        assert "product" in content
        assert "revenue" in content

    def test_data_summary_in_output(self, ctx_with_data: PipelineContext) -> None:
        stage = S3DataLoadStage()
        output = stage.run(ctx_with_data)

        assert "tables" in output.data
        assert "sales" in output.data["tables"]
        assert output.data["tables"]["sales"]["rows"] == 2
        assert output.data["tables"]["sales"]["cols"] == 3

    def test_get_artifacts(self, ctx_with_data: PipelineContext) -> None:
        stage = S3DataLoadStage()
        artifacts = stage.get_artifacts(ctx_with_data)
        assert ".anappt/s3_data_profile.md" in artifacts

    def test_no_llm_call(self, ctx_with_data: PipelineContext) -> None:
        """S3 should not use the LLM."""
        stage = S3DataLoadStage()
        stage.run(ctx_with_data)
        ctx_with_data.llm.chat.assert_not_called()

    def test_nonexistent_data_dir(self, tmp_path: Path, config: ReportConfig) -> None:
        """Handle missing data directory gracefully."""
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=config,
            llm=MagicMock(),
            state=state,
        )
        # Don't create data directory
        stage = S3DataLoadStage()
        output = stage.run(ctx)
        assert output.success is False


class TestS3Prerequisites:
    """Tests for validate_prerequisites."""

    def test_requires_s2_completed(self, tmp_path: Path) -> None:
        from anappt.io.state import StageStatus

        state = StateManager(tmp_path / "state.yaml")
        stage = S3DataLoadStage()

        assert stage.validate_prerequisites(state) is False

        # Complete S1 and S2
        for sid in ["S1", "S2"]:
            state.transition(sid, StageStatus.IN_PROGRESS)
            state.transition(sid, StageStatus.AWAITING_REVIEW)
            state.transition(sid, StageStatus.COMPLETED)

        assert stage.validate_prerequisites(state) is True
