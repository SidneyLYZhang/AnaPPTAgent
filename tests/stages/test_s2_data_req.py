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


# ---------------------------------------------------------------------------
# Declarative metadata tests (Task B3)
# ---------------------------------------------------------------------------


class TestS2Declarative:
    """Tests for the declarative interface added in Task B3."""

    def test_goal_is_s2_goal_key(self) -> None:
        assert S2DataRequirementStage().goal == "s2.goal"

    def test_goal_i18n_resolves(self) -> None:
        """``s2.goal`` should resolve to a non-empty localized string."""
        from anappt.i18n import set_locale, t

        set_locale("zh")
        text = t(S2DataRequirementStage().goal)
        assert text
        assert text != "s2.goal"  # not a missing-key fallback

    def test_get_artifacts_returns_s2_data_requirement(
        self, tmp_path: Path
    ) -> None:
        """get_artifacts returns the expected S2 artifact path."""
        empty_config = ReportConfig()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=empty_config,
            llm=MagicMock(),
            state=state,
        )
        artifacts = S2DataRequirementStage().get_artifacts(ctx)
        assert artifacts == [".anappt/s2_data_requirement.md"]

    def test_system_prompt_fragment_nonempty(self, tmp_path: Path) -> None:
        empty_config = ReportConfig()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=empty_config,
            llm=MagicMock(),
            state=state,
        )
        fragment = S2DataRequirementStage().system_prompt_fragment(ctx)
        assert isinstance(fragment, str)
        assert len(fragment) > 0

    def test_system_prompt_fragment_contains_key_actions(
        self, tmp_path: Path
    ) -> None:
        """The prompt must mention the key S2 actions per spec B3."""
        empty_config = ReportConfig()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=empty_config,
            llm=MagicMock(),
            state=state,
        )
        fragment = S2DataRequirementStage().system_prompt_fragment(ctx)
        # Spec B3: derive data requirements (数据需求) from analysis needs.
        assert "数据需求" in fragment
        # Must mention reading report.yaml and s1_topic.md.
        assert "report.yaml" in fragment
        assert "s1_topic.md" in fragment
        # Must mention the artifact to write.
        assert "s2_data_requirement.md" in fragment
        # Must instruct the LLM to wait for user confirm.
        assert "confirm" in fragment
        # Must explicitly say not to check data existence.
        assert "不检查数据是否实际存在" in fragment or "不检查数据是否存在" in fragment

    def test_system_prompt_fragment_contains_write_artifact_guidance(
        self, tmp_path: Path
    ) -> None:
        empty_config = ReportConfig()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=empty_config,
            llm=MagicMock(),
            state=state,
        )
        fragment = S2DataRequirementStage().system_prompt_fragment(ctx)
        assert "write_artifact" in fragment

    def test_tools_returns_expected_subset(self, tmp_path: Path) -> None:
        empty_config = ReportConfig()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=empty_config,
            llm=MagicMock(),
            state=state,
        )
        tools = S2DataRequirementStage().tools(ctx)
        assert tools == [
            "read_file",
            "write_artifact",
            "read_memory",
            "update_memory",
            "read_history",
        ]

    def test_is_ready_false_when_artifact_missing(self, tmp_path: Path) -> None:
        """Empty project dir → artifact missing → is_ready False."""
        empty_config = ReportConfig()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=empty_config,
            llm=MagicMock(),
            state=state,
        )
        assert S2DataRequirementStage().is_ready(ctx) is False

    def test_is_ready_false_when_artifact_empty(self, tmp_path: Path) -> None:
        """Artifact exists but is empty → False."""
        empty_config = ReportConfig()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=empty_config,
            llm=MagicMock(),
            state=state,
        )
        artifact_path = tmp_path / ".anappt" / "s2_data_requirement.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("   \n  \n", encoding="utf-8")
        assert S2DataRequirementStage().is_ready(ctx) is False

    def test_is_ready_false_when_no_heading_or_list_item(
        self, tmp_path: Path
    ) -> None:
        """Artifact has plain text but no heading or list item → False."""
        empty_config = ReportConfig()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=empty_config,
            llm=MagicMock(),
            state=state,
        )
        artifact_path = tmp_path / ".anappt" / "s2_data_requirement.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            "这是一段纯文本没有标题也没有列表项", encoding="utf-8"
        )
        assert S2DataRequirementStage().is_ready(ctx) is False

    def test_is_ready_true_when_artifact_nonempty(self, tmp_path: Path) -> None:
        """Artifact exists with non-empty content → True."""
        empty_config = ReportConfig()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=empty_config,
            llm=MagicMock(),
            state=state,
        )
        artifact_path = tmp_path / ".anappt" / "s2_data_requirement.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("# 数据需求清单\n\n内容", encoding="utf-8")
        assert S2DataRequirementStage().is_ready(ctx) is True
