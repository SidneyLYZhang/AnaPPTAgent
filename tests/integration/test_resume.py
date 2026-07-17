"""Integration test: Pipeline interruption and resume.

Tests that the pipeline correctly persists state to disk and can resume
from the correct stage after an orchestrator restart.

Task 8.2 — Integration test: interruption and resume.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import yaml

from anappt.io.state import StageStatus, StateManager
from anappt.orchestrator import Orchestrator
from anappt.types import PipelineContext


class TestResumePipeline:
    """Integration tests for pipeline interruption and resume."""

    def test_resume_from_s4_after_s3_confirmed(
        self,
        integration_project: Path,
        mock_llm_for_pipeline: MagicMock,
        make_context: object,
        all_stages: list,
        mock_ppt_bridge: object,
    ) -> None:
        """After S3 confirmed (S4 awaiting_review), resume should show S4.

        Flow:
        1. Run S1-S3 and confirm each (S4 runs automatically, is awaiting_review)
        2. Exit — destroy the orchestrator
        3. Create new Orchestrator with fresh StateManager (loads from state.yaml)
        4. Resume -> S4 should be awaiting_review (NOT re-executed)
        5. Confirm S4, S5, S6 to complete the pipeline
        """
        project_dir = integration_project

        # --- Phase 1: Run S1-S3 with first orchestrator ---
        ctx1: PipelineContext = make_context(mock_llm_for_pipeline)
        orch1 = Orchestrator()
        orch1.register_stages(all_stages)
        orch1.set_context(ctx1)

        orch1.run()  # S1 runs -> awaiting_review
        orch1.confirm()  # S1 done, S2 runs -> awaiting_review
        orch1.confirm()  # S2 done, S3 runs -> awaiting_review
        orch1.confirm()  # S3 done, S4 runs -> awaiting_review

        # Verify S4 is awaiting_review
        assert ctx1.state.get_stage("S4").status == StageStatus.AWAITING_REVIEW
        assert ctx1.state.state.current_stage == "S4"

        # Record LLM call counts before resume
        chat_calls_before = mock_llm_for_pipeline.chat.call_count
        chat_with_tools_before = mock_llm_for_pipeline.chat_with_tools.call_count

        # --- Phase 2: Create new orchestrator (same LLM, fresh StateManager) ---
        ctx2: PipelineContext = make_context(mock_llm_for_pipeline)

        # Verify state was persisted and loaded correctly
        assert ctx2.state.get_stage("S1").status == StageStatus.COMPLETED
        assert ctx2.state.get_stage("S2").status == StageStatus.COMPLETED
        assert ctx2.state.get_stage("S3").status == StageStatus.COMPLETED
        assert ctx2.state.get_stage("S4").status == StageStatus.AWAITING_REVIEW
        assert ctx2.state.state.current_stage == "S4"

        orch2 = Orchestrator()
        orch2.register_stages(all_stages)
        orch2.set_context(ctx2)

        # Resume — should show S4 awaiting_review without re-running
        result = orch2.resume()
        assert result["completed"] is False
        assert result["stage_id"] == "S4"

        # LLM should NOT have been called during resume (S4 not re-executed)
        assert mock_llm_for_pipeline.chat.call_count == chat_calls_before
        assert mock_llm_for_pipeline.chat_with_tools.call_count == chat_with_tools_before

        # S4 should still be awaiting_review
        assert ctx2.state.get_stage("S4").status == StageStatus.AWAITING_REVIEW

        # --- Phase 3: Confirm S4, S5, S6 to complete pipeline ---
        with mock_ppt_bridge(project_dir):
            # Confirm S4 -> S5 runs
            result = orch2.confirm()
            assert result["confirmed"]
            assert result["next_stage"] == "S5"

            # Confirm S5 -> S6 runs
            result = orch2.confirm()
            assert result["confirmed"]
            assert result["next_stage"] == "S6"

            # Confirm S6 -> pipeline complete
            result = orch2.confirm()
            assert result["confirmed"]
            assert result["next_stage"] is None

        # Pipeline should be complete
        assert ctx2.state.is_pipeline_complete()

        # Verify key artifacts exist
        assert (project_dir / ".anappt" / "s4_analysis_report.md").exists()
        assert (project_dir / "output" / "report.md").exists()
        assert (project_dir / "output" / "ppt" / "presentation.html").exists()

    def test_resume_awaiting_review_not_rerun(
        self,
        integration_project: Path,
        mock_llm_for_pipeline: MagicMock,
        make_context: object,
        all_stages: list,
    ) -> None:
        """S4 awaiting_review -> resume shows awaiting_review, not re-execute.

        Verifies that the awaiting_review state is preserved across
        orchestrator restarts and the stage is NOT re-executed.
        """
        project_dir = integration_project

        # --- Phase 1: Run S1-S3 ---
        ctx1: PipelineContext = make_context(mock_llm_for_pipeline)
        orch1 = Orchestrator()
        orch1.register_stages(all_stages)
        orch1.set_context(ctx1)

        orch1.run()
        orch1.confirm()  # S1 -> S2
        orch1.confirm()  # S2 -> S3
        orch1.confirm()  # S3 -> S4 awaiting_review

        # Record S4 artifact modification time before resume
        s4_artifact = project_dir / ".anappt" / "s4_analysis_report.md"
        assert s4_artifact.exists(), "S4 artifact should exist after S4 runs"
        mtime_before = s4_artifact.stat().st_mtime

        # --- Phase 2: Create new orchestrator with fresh LLM ---
        fresh_mock_llm = MagicMock()
        ctx2: PipelineContext = make_context(fresh_mock_llm)

        orch2 = Orchestrator()
        orch2.register_stages(all_stages)
        orch2.set_context(ctx2)

        # Resume — should show S4 awaiting_review
        result = orch2.resume()
        assert result["stage_id"] == "S4"
        assert result["completed"] is False

        # S4 should still be awaiting_review
        assert ctx2.state.get_stage("S4").status == StageStatus.AWAITING_REVIEW

        # LLM was NOT called during resume
        fresh_mock_llm.chat.assert_not_called()
        fresh_mock_llm.chat_with_tools.assert_not_called()

        # S4 artifact was NOT modified during resume
        mtime_after = s4_artifact.stat().st_mtime
        assert mtime_after == mtime_before, "S4 artifact should not be modified during resume"

    def test_reset_restarts_from_s1(
        self,
        integration_project: Path,
        mock_llm_for_pipeline: MagicMock,
        make_context: object,
        all_stages: list,
    ) -> None:
        """reset() should clear all stages and restart from S1 (--from-scratch).

        Flow:
        1. Run S1-S3 and confirm (S4 is awaiting_review)
        2. Call reset()
        3. All stages should be pending, current_stage = S1
        4. run() should start from S1 again
        """
        ctx: PipelineContext = make_context(mock_llm_for_pipeline)
        orch = Orchestrator()
        orch.register_stages(all_stages)
        orch.set_context(ctx)

        # Run S1-S3
        orch.run()
        orch.confirm()  # S1 -> S2
        orch.confirm()  # S2 -> S3
        orch.confirm()  # S3 -> S4

        # Verify we're at S4 awaiting_review
        assert ctx.state.get_stage("S4").status == StageStatus.AWAITING_REVIEW

        # Reset (--from-scratch)
        result = orch.reset()
        assert result["reset"] is True

        # All stages should be pending
        for stage in ctx.state.get_all_stages():
            assert stage.status == StageStatus.PENDING, (
                f"Stage {stage.id} should be pending after reset, got {stage.status}"
            )

        # current_stage should be S1
        assert ctx.state.state.current_stage == "S1"

        # started_at, completed_at, and iteration should be cleared
        for stage in ctx.state.get_all_stages():
            assert stage.started_at is None, (
                f"Stage {stage.id} started_at should be None after reset"
            )
            assert stage.completed_at is None, (
                f"Stage {stage.id} completed_at should be None after reset"
            )
            assert stage.iteration == 0, f"Stage {stage.id} iteration should be 0 after reset"

        # run() should start from S1
        result = orch.run()
        assert result["stage_id"] == "S1"
        assert result["completed"] is False

        # S1 should be awaiting_review after run
        assert ctx.state.get_stage("S1").status == StageStatus.AWAITING_REVIEW

        # Verify state was persisted to disk
        state_file = integration_project / ".anappt" / "state.yaml"
        assert state_file.exists()
        with open(state_file, encoding="utf-8") as f:
            state_data = yaml.safe_load(f)
        assert state_data["current_stage"] == "S1"
        for stage_data in state_data["stages"]:
            if stage_data["id"] == "S1":
                assert stage_data["status"] == "awaiting_review"
            else:
                assert stage_data["status"] == "pending"

    def test_state_persistence_across_orchestrators(
        self,
        integration_project: Path,
        mock_llm_for_pipeline: MagicMock,
        make_context: object,
        all_stages: list,
    ) -> None:
        """Verify state is persisted to disk and loadable by a new StateManager.

        After running S1-S2 and confirming (S3 awaiting_review), the state
        file on disk should reflect the current pipeline state.
        """
        project_dir = integration_project

        ctx1: PipelineContext = make_context(mock_llm_for_pipeline)
        orch1 = Orchestrator()
        orch1.register_stages(all_stages)
        orch1.set_context(ctx1)

        # Run S1-S2
        orch1.run()
        orch1.confirm()  # S1 -> S2
        orch1.confirm()  # S2 -> S3

        # Verify state file exists on disk
        state_file = project_dir / ".anappt" / "state.yaml"
        assert state_file.exists(), "state.yaml should exist on disk"

        # Create new StateManager from the same file (simulates restart)
        state2 = StateManager(state_file)

        # Verify state was loaded correctly
        assert state2.get_stage("S1").status == StageStatus.COMPLETED
        assert state2.get_stage("S2").status == StageStatus.COMPLETED
        assert state2.get_stage("S3").status == StageStatus.AWAITING_REVIEW
        assert state2.state.current_stage == "S3"

        # Verify timestamps were persisted
        s1 = state2.get_stage("S1")
        assert s1.started_at is not None, "S1 started_at should be persisted"
        assert s1.completed_at is not None, "S1 completed_at should be persisted"

        # Create another PipelineContext with the loaded state
        # and verify resume works
        fresh_llm = MagicMock()
        ctx2: PipelineContext = make_context(fresh_llm)
        orch2 = Orchestrator()
        orch2.register_stages(all_stages)
        orch2.set_context(ctx2)

        result = orch2.resume()
        assert result["stage_id"] == "S3"
        assert result["completed"] is False

        # LLM should not be called (S3 is awaiting_review)
        fresh_llm.chat.assert_not_called()
