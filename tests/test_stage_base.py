"""Tests for StageBase abstract class."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.state import StateManager
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput


class MockStage(StageBase):
    """Mock stage implementation for testing."""

    stage_id: str = "S1"
    stage_name: str = "stage.s1.name"

    def run(self, ctx: PipelineContext) -> StageOutput:
        return StageOutput(
            success=True,
            artifacts=["test.md"],
            summary="Mock stage completed",
            next_action="confirm",
        )

    def get_artifacts(self, ctx: PipelineContext) -> list[str]:
        return ["test.md"]


class MockStageS2(StageBase):
    """Mock stage for S2 testing."""

    stage_id: str = "S2"
    stage_name: str = "stage.s2.name"

    def run(self, ctx: PipelineContext) -> StageOutput:
        return StageOutput(success=True, summary="S2 done")


@pytest.fixture
def state(tmp_path: Path) -> StateManager:
    """Return a fresh StateManager."""
    return StateManager(tmp_path / "state.yaml")


@pytest.fixture
def mock_ctx(tmp_path: Path, state: StateManager) -> PipelineContext:
    """Return a mock pipeline context."""
    return PipelineContext(
        project_dir=tmp_path,
        config=MagicMock(),
        llm=MagicMock(),
        state=state,
    )


class TestStageBaseAttributes:
    """Tests for stage attributes and properties."""

    def test_stage_id(self) -> None:
        stage = MockStage()
        assert stage.stage_id == "S1"

    def test_stage_name(self) -> None:
        stage = MockStage()
        assert stage.stage_name == "stage.s1.name"

    def test_model_role_s1(self) -> None:
        stage = MockStage()
        assert stage.model_role == "reasoning"

    def test_model_role_s2(self) -> None:
        stage = MockStageS2()
        assert stage.model_role == "reasoning"

    def test_model_role_s4(self) -> None:
        class S4Stage(StageBase):
            stage_id = "S4"
            stage_name = "stage.s4.name"

            def run(self, ctx: PipelineContext) -> StageOutput:
                return StageOutput()

        assert S4Stage().model_role == "analysis"

    def test_model_role_s5(self) -> None:
        class S5Stage(StageBase):
            stage_id = "S5"
            stage_name = "stage.s5.name"

            def run(self, ctx: PipelineContext) -> StageOutput:
                return StageOutput()

        assert S5Stage().model_role == "writing"

    def test_display_name(self) -> None:
        from anappt.i18n import set_locale

        set_locale("zh")
        stage = MockStage()
        name = stage.display_name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_display_name_en(self) -> None:
        from anappt.i18n import set_locale

        set_locale("en")
        stage = MockStage()
        name = stage.display_name()
        assert isinstance(name, str)
        assert len(name) > 0
        set_locale("zh")


class TestStageBaseRun:
    """Tests for the run method."""

    def test_run_returns_output(self, mock_ctx: PipelineContext) -> None:
        stage = MockStage()
        output = stage.run(mock_ctx)
        assert output.success is True
        assert output.artifacts == ["test.md"]
        assert output.summary == "Mock stage completed"
        assert output.next_action == "confirm"

    def test_get_artifacts_default(self, mock_ctx: PipelineContext) -> None:
        class CustomStage(StageBase):
            stage_id = "S3"
            stage_name = "stage.s3.name"

            def run(self, ctx: PipelineContext) -> StageOutput:
                return StageOutput()

        stage = CustomStage()
        assert stage.get_artifacts(mock_ctx) == []

    def test_get_artifacts_override(self, mock_ctx: PipelineContext) -> None:
        stage = MockStage()
        assert stage.get_artifacts(mock_ctx) == ["test.md"]


class TestStageBaseDeclarative:
    """Tests for the declarative interface: goal, system_prompt_fragment,
    tools, and is_ready default behaviors."""

    def test_goal_default_empty(self) -> None:
        stage = MockStage()
        assert stage.goal == ""

    def test_goal_subclass_override(self) -> None:
        class GoalStage(StageBase):
            stage_id = "S1"
            stage_name = "stage.s1.name"
            goal = "s1.goal"

            def run(self, ctx: PipelineContext) -> StageOutput:
                return StageOutput()

        assert GoalStage().goal == "s1.goal"

    def test_system_prompt_fragment_default_empty(
        self, mock_ctx: PipelineContext
    ) -> None:
        class PlainStage(StageBase):
            stage_id = "S3"
            stage_name = "stage.s3.name"

            def run(self, ctx: PipelineContext) -> StageOutput:
                return StageOutput()

        assert PlainStage().system_prompt_fragment(mock_ctx) == ""

    def test_system_prompt_fragment_override(
        self, mock_ctx: PipelineContext
    ) -> None:
        class PromptStage(StageBase):
            stage_id = "S1"
            stage_name = "stage.s1.name"

            def run(self, ctx: PipelineContext) -> StageOutput:
                return StageOutput()

            def system_prompt_fragment(self, ctx: PipelineContext) -> str:
                return "You are an analyst."

        assert PromptStage().system_prompt_fragment(mock_ctx) == "You are an analyst."

    def test_tools_default_empty(self, mock_ctx: PipelineContext) -> None:
        class PlainStage(StageBase):
            stage_id = "S3"
            stage_name = "stage.s3.name"

            def run(self, ctx: PipelineContext) -> StageOutput:
                return StageOutput()

        assert PlainStage().tools(mock_ctx) == []

    def test_tools_override(self, mock_ctx: PipelineContext) -> None:
        class ToolStage(StageBase):
            stage_id = "S4"
            stage_name = "stage.s4.name"

            def run(self, ctx: PipelineContext) -> StageOutput:
                return StageOutput()

            def tools(self, ctx: PipelineContext) -> list[str]:
                return ["execute_python", "search_web"]

        assert ToolStage().tools(mock_ctx) == ["execute_python", "search_web"]

    def test_is_ready_default_no_artifacts(self, mock_ctx: PipelineContext) -> None:
        """Stage declaring no artifacts is_ready by default."""

        class PlainStage(StageBase):
            stage_id = "S3"
            stage_name = "stage.s3.name"

            def run(self, ctx: PipelineContext) -> StageOutput:
                return StageOutput()

        assert PlainStage().is_ready(mock_ctx) is True

    def test_is_ready_default_artifacts_all_exist(
        self, mock_ctx: PipelineContext
    ) -> None:
        """Default is_ready True when all declared artifacts exist on disk."""

        class ReadyStage(StageBase):
            stage_id = "S1"
            stage_name = "stage.s1.name"

            def run(self, ctx: PipelineContext) -> StageOutput:
                return StageOutput()

            def get_artifacts(self, ctx: PipelineContext) -> list[str]:
                return ["a.md", "sub/b.md"]

        # Pre-create both files under the project dir.
        (mock_ctx.project_dir / "a.md").write_text("x", encoding="utf-8")
        (mock_ctx.project_dir / "sub").mkdir(parents=True, exist_ok=True)
        (mock_ctx.project_dir / "sub" / "b.md").write_text("y", encoding="utf-8")

        assert ReadyStage().is_ready(mock_ctx) is True

    def test_is_ready_default_missing_artifact(
        self, mock_ctx: PipelineContext
    ) -> None:
        """Default is_ready False when at least one declared artifact is missing."""

        class PartialStage(StageBase):
            stage_id = "S1"
            stage_name = "stage.s1.name"

            def run(self, ctx: PipelineContext) -> StageOutput:
                return StageOutput()

            def get_artifacts(self, ctx: PipelineContext) -> list[str]:
                return ["present.md", "missing.md"]

        (mock_ctx.project_dir / "present.md").write_text("x", encoding="utf-8")
        # Note: missing.md is intentionally not created.

        assert PartialStage().is_ready(mock_ctx) is False


class TestStageBasePrerequisites:
    """Tests for validate_prerequisites method."""

    def test_s1_no_prerequisites(self, state: StateManager) -> None:
        stage = MockStage()
        assert stage.validate_prerequisites(state) is True

    def test_s2_requires_s1_completed(self, state: StateManager) -> None:
        stage = MockStageS2()
        # S1 not completed yet
        assert stage.validate_prerequisites(state) is False

    def test_s2_s1_in_progress(self, state: StateManager) -> None:
        from anappt.io.state import StageStatus

        stage = MockStageS2()
        state.transition("S1", StageStatus.IN_PROGRESS)
        assert stage.validate_prerequisites(state) is False

    def test_s2_s1_awaiting_review(self, state: StateManager) -> None:
        from anappt.io.state import StageStatus

        stage = MockStageS2()
        state.transition("S1", StageStatus.IN_PROGRESS)
        state.transition("S1", StageStatus.AWAITING_REVIEW)
        assert stage.validate_prerequisites(state) is False

    def test_s2_s1_completed(self, state: StateManager) -> None:
        from anappt.io.state import StageStatus

        stage = MockStageS2()
        state.transition("S1", StageStatus.IN_PROGRESS)
        state.transition("S1", StageStatus.AWAITING_REVIEW)
        state.transition("S1", StageStatus.COMPLETED)
        assert stage.validate_prerequisites(state) is True


class TestStageBaseUILogging:
    """Tests for UI and session logging helpers."""

    def test_log_ui_with_ui(self, mock_ctx: PipelineContext) -> None:
        ui = MagicMock()
        mock_ctx.ui = ui
        stage = MockStage()
        stage._log_ui(mock_ctx, "test message")
        ui.print.assert_called_once_with("test message")

    def test_log_ui_without_ui(self, mock_ctx: PipelineContext) -> None:
        mock_ctx.ui = None
        stage = MockStage()
        # Should not raise
        stage._log_ui(mock_ctx, "test message")

    def test_log_session_with_session(self, mock_ctx: PipelineContext) -> None:
        session = MagicMock()
        mock_ctx.session = session
        stage = MockStage()
        stage._log_session(mock_ctx, "agent content")
        session.log_agent.assert_called_once_with("agent content")

    def test_log_session_without_session(self, mock_ctx: PipelineContext) -> None:
        mock_ctx.session = None
        stage = MockStage()
        # Should not raise
        stage._log_session(mock_ctx, "agent content")


class TestStageBaseAbstract:
    """Tests that StageBase is properly abstract."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            StageBase()  # type: ignore[abstract]
