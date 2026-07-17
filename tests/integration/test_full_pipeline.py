"""Integration test: Full pipeline S1-S6 end-to-end.

Tests that the complete pipeline runs from project creation through all
six stages, producing expected output artifacts at each step.

Task 8.1 — Integration test: full pipeline.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from anappt.io.state import StageStatus
from anappt.orchestrator import Orchestrator
from anappt.types import PipelineContext


class TestFullPipeline:
    """End-to-end integration test for the full S1-S6 pipeline."""

    def test_full_pipeline_e2e(
        self,
        integration_project: Path,
        mock_llm_for_pipeline: MagicMock,
        make_context: object,
        all_stages: list,
        mock_ppt_bridge: object,
    ) -> None:
        """Test that the full pipeline runs S1-S6 and produces all artifacts.

        Flow:
        1. Create project with create_project()
        2. Mock LLM returns canned responses for each role
        3. Mock DashiPPTBridge.generate_ppt creates a mock HTML file
        4. Run S1 -> confirm -> S2 -> confirm -> ... -> S6 -> confirm
        5. Verify all output files, state, and git commits
        """
        project_dir = integration_project
        ctx: PipelineContext = make_context(mock_llm_for_pipeline)

        # Create orchestrator with all stages
        orch = Orchestrator()
        orch.register_stages(all_stages)
        orch.set_context(ctx)

        # Mock DashiPPTBridge during pipeline execution
        with mock_ppt_bridge(project_dir):
            # --- Run through all stages ---

            # S1: run -> awaiting_review
            result = orch.run()
            assert not result["completed"]
            assert result["stage_id"] == "S1"

            # Confirm S1 -> S2 runs -> awaiting_review
            result = orch.confirm()
            assert result["confirmed"]
            assert result["next_stage"] == "S2"

            # Confirm S2 -> S3 runs -> awaiting_review
            result = orch.confirm()
            assert result["confirmed"]
            assert result["next_stage"] == "S3"

            # Confirm S3 -> S4 runs -> awaiting_review
            result = orch.confirm()
            assert result["confirmed"]
            assert result["next_stage"] == "S4"

            # Confirm S4 -> S5 runs -> awaiting_review
            result = orch.confirm()
            assert result["confirmed"]
            assert result["next_stage"] == "S5"

            # Confirm S5 -> S6 runs -> awaiting_review
            result = orch.confirm()
            assert result["confirmed"]
            assert result["next_stage"] == "S6"

            # Confirm S6 -> pipeline complete
            result = orch.confirm()
            assert result["confirmed"]
            assert result["next_stage"] is None

        # --- Verify output files exist ---

        # 1. report.yaml exists and is parseable
        report_yaml = project_dir / "report.yaml"
        assert report_yaml.exists(), "report.yaml should exist"
        with open(report_yaml, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
        assert yaml_data is not None, "report.yaml should be parseable"

        # 2. .anappt/s1_topic.md exists
        assert (project_dir / ".anappt" / "s1_topic.md").exists()

        # 3. .anappt/s2_data_requirement.md exists
        assert (project_dir / ".anappt" / "s2_data_requirement.md").exists()

        # 4. .anappt/s3_data_profile.md exists
        assert (project_dir / ".anappt" / "s3_data_profile.md").exists()

        # 5. .anappt/s4_analysis_report.md exists
        assert (project_dir / ".anappt" / "s4_analysis_report.md").exists()

        # 6. output/report.md exists
        report_md = project_dir / "output" / "report.md"
        assert report_md.exists(), "output/report.md should exist"

        # 7. PPT output file exists (mock)
        ppt_html = project_dir / "output" / "ppt" / "presentation.html"
        assert ppt_html.exists(), "PPT output file should exist"

        # 8. .anappt/s5_report.md exists (copy)
        assert (project_dir / ".anappt" / "s5_report.md").exists()

        # --- Verify state.yaml ---
        assert ctx.state.is_pipeline_complete()
        for stage in ctx.state.get_all_stages():
            assert stage.status == StageStatus.COMPLETED, (
                f"Stage {stage.id} should be completed, got {stage.status}"
            )

        # --- Verify git log has commit records ---
        git_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert git_log.returncode == 0
        commits = git_log.stdout.strip().split("\n")
        # At least: initial commit + stage/confirm commits
        assert len(commits) >= 2, f"Expected at least 2 git commits, got {len(commits)}"

        # --- Verify LLM was called appropriately ---
        # S1: reasoning chat, S2: reasoning chat, S4: analysis chat_with_tools, S5: writing chat
        assert mock_llm_for_pipeline.chat.call_count >= 3  # S1, S2, S5
        assert mock_llm_for_pipeline.chat_with_tools.call_count >= 1  # S4

    def test_pipeline_artifact_content(
        self,
        integration_project: Path,
        mock_llm_for_pipeline: MagicMock,
        make_context: object,
        all_stages: list,
        mock_ppt_bridge: object,
    ) -> None:
        """Verify that stage artifacts contain meaningful content."""
        project_dir = integration_project
        ctx: PipelineContext = make_context(mock_llm_for_pipeline)

        orch = Orchestrator()
        orch.register_stages(all_stages)
        orch.set_context(ctx)

        with mock_ppt_bridge(project_dir):
            orch.run()
            for _ in range(6):
                orch.confirm()

        # S1 artifact: topic document with headings
        s1 = (project_dir / ".anappt" / "s1_topic.md").read_text(encoding="utf-8")
        assert len(s1) > 0
        assert "#" in s1

        # S2 artifact: data requirement document
        s2 = (project_dir / ".anappt" / "s2_data_requirement.md").read_text(encoding="utf-8")
        assert len(s2) > 0

        # S3 artifact: data profile with Data Profile header
        s3 = (project_dir / ".anappt" / "s3_data_profile.md").read_text(encoding="utf-8")
        assert len(s3) > 0
        assert "Data Profile" in s3
        assert "sample" in s3  # References the CSV file name

        # S4 artifact: analysis report
        s4 = (project_dir / ".anappt" / "s4_analysis_report.md").read_text(encoding="utf-8")
        assert len(s4) > 0
        assert "#" in s4

        # S5 artifact: final report
        report = (project_dir / "output" / "report.md").read_text(encoding="utf-8")
        assert len(report) > 0
        assert "#" in report

        # S6 artifact: HTML presentation
        ppt = (project_dir / "output" / "ppt" / "presentation.html").read_text(encoding="utf-8")
        assert len(ppt) > 0

    def test_pipeline_state_yaml_persisted(
        self,
        integration_project: Path,
        mock_llm_for_pipeline: MagicMock,
        make_context: object,
        all_stages: list,
        mock_ppt_bridge: object,
    ) -> None:
        """Verify state.yaml is persisted to disk with all stages completed."""
        project_dir = integration_project
        ctx: PipelineContext = make_context(mock_llm_for_pipeline)

        orch = Orchestrator()
        orch.register_stages(all_stages)
        orch.set_context(ctx)

        with mock_ppt_bridge(project_dir):
            orch.run()
            for _ in range(6):
                orch.confirm()

        # Read state.yaml directly from disk
        state_file = project_dir / ".anappt" / "state.yaml"
        assert state_file.exists(), "state.yaml should exist on disk"

        with open(state_file, encoding="utf-8") as f:
            state_data = yaml.safe_load(f)

        assert state_data is not None
        assert "stages" in state_data
        assert len(state_data["stages"]) == 6

        for stage_data in state_data["stages"]:
            assert stage_data["status"] == "completed", (
                f"Stage {stage_data['id']} should be completed in state.yaml"
            )
            assert stage_data["completed_at"] is not None, (
                f"Stage {stage_data['id']} should have completed_at timestamp"
            )

    def test_pipeline_intermediate_state_during_run(
        self,
        integration_project: Path,
        mock_llm_for_pipeline: MagicMock,
        make_context: object,
        all_stages: list,
    ) -> None:
        """Verify intermediate state transitions during pipeline execution."""
        ctx: PipelineContext = make_context(mock_llm_for_pipeline)

        orch = Orchestrator()
        orch.register_stages(all_stages)
        orch.set_context(ctx)

        # Initial state: all pending, current = S1
        assert ctx.state.state.current_stage == "S1"
        assert ctx.state.get_stage("S1").status == StageStatus.PENDING

        # Run S1
        orch.run()
        assert ctx.state.get_stage("S1").status == StageStatus.AWAITING_REVIEW
        assert ctx.state.state.current_stage == "S1"

        # Confirm S1 -> S2 runs
        orch.confirm()
        assert ctx.state.get_stage("S1").status == StageStatus.COMPLETED
        assert ctx.state.get_stage("S2").status == StageStatus.AWAITING_REVIEW
        assert ctx.state.state.current_stage == "S2"

        # Confirm S2 -> S3 runs
        orch.confirm()
        assert ctx.state.get_stage("S2").status == StageStatus.COMPLETED
        assert ctx.state.get_stage("S3").status == StageStatus.AWAITING_REVIEW
        assert ctx.state.state.current_stage == "S3"
