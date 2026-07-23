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
        assert "output/final_report.md" in artifacts

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


# ---------------------------------------------------------------------------
# Declarative metadata tests (Task B6)
# ---------------------------------------------------------------------------


def _make_empty_ctx(tmp_path: Path) -> PipelineContext:
    """Return a PipelineContext with an empty ReportConfig."""
    empty_config = ReportConfig()
    state = StateManager(tmp_path / ".anappt" / "state.yaml")
    return PipelineContext(
        project_dir=tmp_path,
        config=empty_config,
        llm=MagicMock(),
        state=state,
    )


class TestS5Declarative:
    """Tests for the declarative interface added in Task B6."""

    def test_goal_is_s5_goal_key(self) -> None:
        assert S5ReportStage().goal == "s5.goal"

    def test_goal_i18n_resolves(self) -> None:
        """``s5.goal`` should resolve to a non-empty localized string."""
        from anappt.i18n import set_locale, t

        set_locale("zh")
        text = t(S5ReportStage().goal)
        assert text
        assert text != "s5.goal"  # not a missing-key fallback

    def test_get_artifacts_returns_final_report(self, tmp_path: Path) -> None:
        """get_artifacts returns the expected S5 artifact path."""
        ctx = _make_empty_ctx(tmp_path)
        artifacts = S5ReportStage().get_artifacts(ctx)
        assert artifacts == ["output/final_report.md"]

    def test_system_prompt_fragment_nonempty(self, tmp_path: Path) -> None:
        ctx = _make_empty_ctx(tmp_path)
        fragment = S5ReportStage().system_prompt_fragment(ctx)
        assert isinstance(fragment, str)
        assert len(fragment) > 0

    def test_system_prompt_fragment_contains_key_actions(
        self, tmp_path: Path
    ) -> None:
        """The prompt must mention the key S5 actions per spec B6."""
        ctx = _make_empty_ctx(tmp_path)
        fragment = S5ReportStage().system_prompt_fragment(ctx)
        # Spec B6: produce final_report.md with standard structure.
        assert "final_report.md" in fragment
        assert "结构" in fragment
        # Must instruct the LLM to wait for user confirm.
        assert "confirm" in fragment

    def test_system_prompt_fragment_contains_write_artifact_guidance(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_empty_ctx(tmp_path)
        fragment = S5ReportStage().system_prompt_fragment(ctx)
        assert "write_artifact" in fragment

    def test_tools_returns_expected_subset(self, tmp_path: Path) -> None:
        ctx = _make_empty_ctx(tmp_path)
        tools = S5ReportStage().tools(ctx)
        assert tools == [
            "read_file",
            "write_artifact",
            "read_memory",
            "update_memory",
            "read_history",
        ]

    def test_is_ready_false_when_artifact_missing(self, tmp_path: Path) -> None:
        """Empty project dir → artifact missing → is_ready False."""
        ctx = _make_empty_ctx(tmp_path)
        assert S5ReportStage().is_ready(ctx) is False

    def test_is_ready_false_when_artifact_empty(self, tmp_path: Path) -> None:
        """Artifact exists but is empty → False."""
        ctx = _make_empty_ctx(tmp_path)
        artifact_path = tmp_path / "output" / "final_report.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("   \n  \n", encoding="utf-8")
        assert S5ReportStage().is_ready(ctx) is False

    def test_is_ready_false_when_fewer_than_2_h1_headings(
        self, tmp_path: Path
    ) -> None:
        """Artifact has only 1 H1 heading → False (spec requires ≥ 2)."""
        ctx = _make_empty_ctx(tmp_path)
        artifact_path = tmp_path / "output" / "final_report.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            "# Final Report\n\nOnly one heading.", encoding="utf-8"
        )
        assert S5ReportStage().is_ready(ctx) is False

    def test_is_ready_true_when_artifact_nonempty(self, tmp_path: Path) -> None:
        """Artifact exists with ≥ 2 H1 headings → True."""
        ctx = _make_empty_ctx(tmp_path)
        artifact_path = tmp_path / "output" / "final_report.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            "# Final Report\n\n内容\n\n## 子标题\n\n# 附录\n\n数据说明",
            encoding="utf-8",
        )
        assert S5ReportStage().is_ready(ctx) is True
