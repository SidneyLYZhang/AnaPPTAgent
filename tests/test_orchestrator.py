"""Tests for the Orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.config import ReportConfig
from anappt.io.state import StageStatus, StateManager
from anappt.orchestrator import Orchestrator
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput


class MockSuccessStage(StageBase):
    """Mock stage that always succeeds."""

    def __init__(self, stage_id: str, stage_name: str = "stage.s1.name") -> None:
        self.stage_id = stage_id
        self.stage_name = stage_name

    def run(self, ctx: PipelineContext) -> StageOutput:
        return StageOutput(
            success=True,
            artifacts=["test.md"],
            summary=f"{self.stage_id} completed",
        )


class MockFailingStage(StageBase):
    """Mock stage that always fails."""

    stage_id: str = "S1"
    stage_name: str = "stage.s1.name"

    def run(self, ctx: PipelineContext) -> StageOutput:
        return StageOutput(
            success=False,
            summary="Mock failure",
            next_action="retry",
        )


@pytest.fixture
def ctx(tmp_path: Path) -> PipelineContext:
    """Return a PipelineContext with mock services."""
    config = ReportConfig()
    llm = MagicMock()
    state = StateManager(tmp_path / ".anappt" / "state.yaml")
    ui = MagicMock()
    session = MagicMock()
    git = MagicMock()
    git.is_git_repo.return_value = False

    return PipelineContext(
        project_dir=tmp_path,
        config=config,
        llm=llm,
        state=state,
        ui=ui,
        session=session,
        git=git,
    )


@pytest.fixture
def orch() -> Orchestrator:
    """Return an empty Orchestrator."""
    return Orchestrator()


class TestOrchestratorRegistration:
    """Tests for stage registration."""

    def test_register_single_stage(self, orch: Orchestrator) -> None:
        stage = MockSuccessStage("S1")
        orch.register_stage(stage)
        assert "S1" in orch.stages

    def test_register_multiple_stages(self, orch: Orchestrator) -> None:
        stages = [MockSuccessStage("S1"), MockSuccessStage("S2", "stage.s2.name")]
        orch.register_stages(stages)
        assert len(orch.stages) == 2
        assert "S1" in orch.stages
        assert "S2" in orch.stages

    def test_register_overwrites(self, orch: Orchestrator) -> None:
        stage1 = MockSuccessStage("S1")
        stage2 = MockSuccessStage("S1")
        orch.register_stage(stage1)
        orch.register_stage(stage2)
        assert orch.stages["S1"] is stage2


class TestOrchestratorContext:
    """Tests for context management."""

    def test_set_context(self, orch: Orchestrator, ctx: PipelineContext) -> None:
        orch.set_context(ctx)
        assert orch.ctx is ctx

    def test_ensure_context_without_setting(self, orch: Orchestrator) -> None:
        with pytest.raises(RuntimeError, match="context not set"):
            orch._ensure_context()

    def test_ensure_context_with_setting(self, orch: Orchestrator, ctx: PipelineContext) -> None:
        orch.set_context(ctx)
        result = orch._ensure_context()
        assert result is ctx


class TestOrchestratorRun:
    """Tests for the run method."""

    def test_run_single_stage(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        """Run should execute S1 and stop at awaiting_review."""
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        result = orch.run()

        assert result["completed"] is False
        assert result["stage_id"] == "S1"
        assert "completed" in result["summary"]

        # Verify state transition
        stage = ctx.state.get_stage("S1")
        assert stage.status == StageStatus.AWAITING_REVIEW

    def test_run_no_stages_raises(self, orch: Orchestrator, ctx: PipelineContext) -> None:
        orch.set_context(ctx)
        with pytest.raises(RuntimeError, match="No registered stages"):
            orch.run()

    def test_run_already_complete(self, orch: Orchestrator, ctx: PipelineContext) -> None:
        """When all stages are completed, should return immediately."""
        from anappt.io.state import StageStatus

        # Mark all stages as completed
        for stage_id in ["S1", "S2", "S3", "S4", "S5", "S6"]:
            state_stage = ctx.state.get_stage(stage_id)
            if state_stage:
                state_stage.status = StageStatus.COMPLETED

        orch.register_stages([MockSuccessStage(f"S{i}") for i in range(1, 7)])
        orch.set_context(ctx)

        result = orch.run()
        assert result["completed"] is True

    def test_run_failing_stage(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stage(MockFailingStage())
        orch.set_context(ctx)

        result = orch.run()

        assert result["completed"] is False
        assert result["stage_id"] == "S1"
        assert "Mock failure" in result["summary"]

    def test_run_calls_git_commit(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        orch.run()

        ctx.git.commit_on_stage_complete.assert_called_once()

    def test_run_logs_to_ui(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        orch.run()

        assert ctx.ui.print.call_count > 0

    def test_run_starts_session(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        orch.run()

        ctx.session.new_session.assert_called_once_with("S1")
        ctx.session.flush.assert_called_once()


class TestOrchestratorConfirm:
    """Tests for the confirm method."""

    def test_confirm_advances_stage(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        """Confirming S1 should advance current_stage to S2."""
        orch.register_stages([MockSuccessStage("S1"), MockSuccessStage("S2", "stage.s2.name")])
        orch.set_context(ctx)

        # Run S1
        orch.run()

        # Confirm S1
        result = orch.confirm()

        assert result["confirmed"] is True
        # State should have advanced
        assert ctx.state.state.current_stage == "S2"

    def test_confirm_calls_git(self, orch: Orchestrator, ctx: PipelineContext) -> None:
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        orch.run()
        orch.confirm()

        ctx.git.commit_on_confirm.assert_called_once()

    def test_confirm_not_awaiting_review(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        """Confirm should fail when stage is not awaiting_review."""
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        result = orch.confirm()
        assert result["confirmed"] is False

    def test_confirm_last_stage_completes_pipeline(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        """Confirming the last remaining stage should complete the pipeline."""
        from anappt.io.state import StageStatus

        # Mark S2-S6 as already completed so S1 is the last one
        for sid in ["S2", "S3", "S4", "S5", "S6"]:
            stage = ctx.state.get_stage(sid)
            if stage is not None:
                stage.status = StageStatus.COMPLETED
                stage.completed_at = "2025-01-01T00:00:00Z"
        # Set current stage back to S1
        ctx.state.state.current_stage = "S1"
        ctx.state.save()

        orch.register_stages([MockSuccessStage("S1")])
        orch.set_context(ctx)

        # Run S1
        orch.run()

        # Confirm S1
        result = orch.confirm()

        assert result["confirmed"] is True
        assert ctx.state.is_pipeline_complete()

    def test_confirm_last_stage_git_exit(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        """Confirming the last stage should trigger git exit commit."""
        orch.register_stages([MockSuccessStage("S1")])
        orch.set_context(ctx)

        orch.run()
        orch.confirm()

        ctx.git.commit_on_exit.assert_called_once()


class TestOrchestratorRevise:
    """Tests for the revise method."""

    def test_revise_reruns_stage(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        # Run S1
        orch.run()

        # Revise with feedback
        result = orch.revise("Please add more detail")

        assert result["revised"] is True
        assert result["stage_id"] == "S1"

        # Stage should be awaiting_review again
        stage = ctx.state.get_stage("S1")
        assert stage.status == StageStatus.AWAITING_REVIEW
        assert stage.iteration == 1

    def test_revise_logs_user_feedback(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        orch.run()
        orch.revise("Add more charts")

        ctx.session.log_user.assert_called_with("Add more charts")

    def test_revise_not_awaiting_review(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        result = orch.revise("feedback")
        assert result["revised"] is False

    def test_revise_calls_git_commit(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        orch.run()
        orch.revise("feedback")

        ctx.git.commit_on_stage_complete.assert_called()


class TestOrchestratorResume:
    """Tests for the resume method."""

    def test_resume_from_current(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stages([MockSuccessStage("S1"), MockSuccessStage("S2", "stage.s2.name")])
        orch.set_context(ctx)

        result = orch.resume()

        assert result["completed"] is False
        assert result["stage_id"] == "S1"


class TestOrchestratorReset:
    """Tests for the reset method."""

    def test_reset_clears_all(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        # Run S1
        orch.run()

        # Reset
        result = orch.reset()

        assert result["reset"] is True
        assert ctx.state.state.current_stage == "S1"
        stage = ctx.state.get_stage("S1")
        assert stage.status == StageStatus.PENDING


class TestOrchestratorGetStatus:
    """Tests for get_status method."""

    def test_returns_all_stages(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stages([MockSuccessStage("S1")])
        orch.set_context(ctx)

        status = orch.get_status()

        # StateManager creates all 6 stages
        assert len(status) == 6
        assert status[0]["id"] == "S1"
        assert status[0]["status"] == "pending"

    def test_status_after_run(
        self, orch: Orchestrator, ctx: PipelineContext
    ) -> None:
        orch.register_stage(MockSuccessStage("S1"))
        orch.set_context(ctx)

        orch.run()
        status = orch.get_status()

        s1_status = next(s for s in status if s["id"] == "S1")
        assert s1_status["status"] == "awaiting_review"
