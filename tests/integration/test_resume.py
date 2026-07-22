"""Integration test: Pipeline interruption and resume.

Tests that the pipeline correctly persists state to disk and can resume
from the correct stage after an orchestrator restart.

Task 8.2 — Integration test: interruption and resume.
Task E2.2 — Conversation-driven resume integration tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from anappt import i18n
from anappt.conversation import ConversationRunner
from anappt.io.config import ReportConfig
from anappt.io.git_auto import GitAutoCommit
from anappt.io.memory import MemoryManager
from anappt.io.session import SessionLogger
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


# ---------------------------------------------------------------------------
# Task E2.2: Conversation-driven resume integration tests
# ---------------------------------------------------------------------------


# Reuse the same artifact contents and helpers as test_full_pipeline.py's
# TestConversationDrivenPipeline. Duplicated here to keep test_resume.py
# self-contained (integration test files don't share a common base).
_RESUME_REPORT_YAML = """\
project:
  name: "Resume Test Project"
  type: "one_time"
  created: "2026-07-22"

report:
  topic: "Q3 渠道 ROI 分析"
  motivation: "评估各渠道拉新效率"
  audience:
    - "增长团队"
  objectives:
    - "识别增长瓶颈"
  success_criteria:
    - "结论有数据支撑"

delivery:
  ppt_pages: "15-20"
  formats: ["pptx", "html"]
  theme_preference: null
"""

_RESUME_S1_TOPIC_MD = "# Refined Topic\n\nDetailed topic document.\n"
_RESUME_S2_MD = (
    "# Data Requirements\n\n"
    "## Metrics\n"
    "- DAU: daily active users\n"
)
_RESUME_S3_MD = "# Data Profile\n\n## sample.csv\n- Rows: 3\n"
_RESUME_S4_MD = "# Analysis Report\n\n## Key Findings\n- Finding 1\n"
_RESUME_S5_MD = (
    "# Executive Summary\n\nComprehensive analysis.\n\n"
    "# Methodology\n\nStatistical methods.\n"
)
_RESUME_S6_GOAL_JSON = json.dumps(
    {
        "title": "Test Report",
        "goal": "Generate test report",
        "audience": ["stakeholders"],
        "owner": "test_user",
        "randomSeed": 42,
        "pageCount": 5,
        "themePack": "theme01",
        "slides": [],
    },
    ensure_ascii=False,
)


class _FakeUI:
    """In-memory UI mock (same as test_full_pipeline.py's _FakeUI)."""

    def __init__(self, inputs: list[str] | None = None) -> None:
        self.inputs: list[str] = list(inputs) if inputs else []
        self.prints: list[str] = []

    def print(self, message: str) -> None:
        self.prints.append(message)

    def input(self, prompt: str) -> str:
        if self.inputs:
            return self.inputs.pop(0)
        return "exit"

    def confirm(self, prompt: str) -> bool:
        return True

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        pass

    def progress(self, message: str) -> None:
        pass


def _wa_call(call_id: str, rel_path: str, content: str) -> dict:
    """Build a write_artifact tool_call dict."""
    return {
        "id": call_id,
        "name": "write_artifact",
        "arguments": json.dumps({"rel_path": rel_path, "content": content}),
    }


def _rd_call(call_id: str, goal_json_path: str, output_html_path: str) -> dict:
    """Build a render_deck tool_call dict."""
    return {
        "id": call_id,
        "name": "render_deck",
        "arguments": json.dumps(
            {
                "goal_json_path": goal_json_path,
                "output_html_path": output_html_path,
            }
        ),
    }


def _make_fake_render_deck(project_dir: Path):
    """Create a fake render_deck closure that resolves relative paths
    against ``project_dir``.

    The render_deck tool passes ``Path(goal_json_path)`` and
    ``Path(output_html_path)`` to ``DashiPPTBridge.render_deck``. When
    the LLM provides relative paths (e.g. ``"output/ppt/presentation.html"``),
    the Path is relative and must be resolved against the project
    directory — otherwise the file would be created relative to CWD.
    """

    def fake_render_deck(
        goal_json_path: str | Path,
        output_html_path: str | Path,
        skill_root: str | Path,
    ) -> Path:
        output_html_path = Path(output_html_path)
        if not output_html_path.is_absolute():
            output_html_path = project_dir / output_html_path
        output_html_path.parent.mkdir(parents=True, exist_ok=True)
        output_html_path.write_text(
            "<!DOCTYPE html><html><body>Mock presentation</body></html>",
            encoding="utf-8",
        )
        return output_html_path

    return fake_render_deck


def _build_conv_ctx(
    project_dir: Path,
    llm: MagicMock,
    ui: _FakeUI,
    config: ReportConfig | None = None,
) -> PipelineContext:
    """Build a PipelineContext with all services needed by ConversationRunner."""
    if config is None:
        config = ReportConfig.from_yaml(project_dir / "report.yaml")
    config.delivery.theme_preference = "default"
    state = StateManager(project_dir / ".anappt" / "state.yaml")
    session = SessionLogger(project_dir / ".anappt" / "session_history")
    git = GitAutoCommit(project_dir)
    memory = MemoryManager(project_dir / ".anappt" / "memory.md")
    mock_skill_manager = MagicMock()
    mock_skill_manager.locate_skill.return_value = str(
        project_dir / "dashi-ppt" / "SKILL.md"
    )
    return PipelineContext(
        project_dir=project_dir,
        config=config,
        llm=llm,
        state=state,
        ui=ui,
        session=session,
        git=git,
        memory=memory,
        skill_manager=mock_skill_manager,
    )


def _make_resume_llm_from_s2() -> MagicMock:
    """Build a mock LLM that drives S2-S6 (for resume from S2 in_progress).

    Returns responses for 5 stage openings (S2-S6), each with 2
    chat_with_tools calls (tool_calls + final text), plus 2 chat calls
    for _finalize.
    """
    mock = MagicMock()
    responses = [
        # S2 opening
        {
            "content": "Writing S2 artifact.",
            "tool_calls": [
                _wa_call("c1", ".anappt/s2_data_requirement.md", _RESUME_S2_MD),
            ],
        },
        {"content": "S2 opening: ready. Please confirm.", "tool_calls": []},
        # S3 opening
        {
            "content": "Writing S3 artifact.",
            "tool_calls": [
                _wa_call("c2", ".anappt/s3_data_profile.md", _RESUME_S3_MD),
            ],
        },
        {"content": "S3 opening: ready. Please confirm.", "tool_calls": []},
        # S4 opening
        {
            "content": "Writing S4 artifact.",
            "tool_calls": [
                _wa_call("c3", ".anappt/s4_analysis_report.md", _RESUME_S4_MD),
            ],
        },
        {"content": "S4 opening: ready. Please confirm.", "tool_calls": []},
        # S5 opening
        {
            "content": "Writing S5 artifact.",
            "tool_calls": [
                _wa_call("c4", "output/final_report.md", _RESUME_S5_MD),
            ],
        },
        {"content": "S5 opening: ready. Please confirm.", "tool_calls": []},
        # S6 opening
        {
            "content": "Constructing goal.json and rendering deck.",
            "tool_calls": [
                _wa_call("c5", "output/ppt/goal.json", _RESUME_S6_GOAL_JSON),
                _rd_call("c6", "output/ppt/goal.json", "output/ppt/presentation.html"),
            ],
        },
        {"content": "S6 opening: PPT rendered. Please confirm.", "tool_calls": []},
    ]
    mock.chat_with_tools.side_effect = responses
    mock.chat.side_effect = ["session summary", "NO_UPDATE"]
    return mock


def _make_s1_only_llm() -> MagicMock:
    """Build a mock LLM that writes report.yaml + s1_topic.md in S1,
    then writes s2_data_requirement.md in S2 (for the no-report.yaml test).

    Returns responses for S1 and S2 openings (4 chat_with_tools calls)
    plus 2 chat calls for _finalize.
    """
    mock = MagicMock()
    responses = [
        # S1 opening: write report.yaml + s1_topic.md
        {
            "content": "Writing S1 artifacts.",
            "tool_calls": [
                _wa_call("c1", "report.yaml", _RESUME_REPORT_YAML),
                _wa_call("c2", ".anappt/s1_topic.md", _RESUME_S1_TOPIC_MD),
            ],
        },
        {"content": "S1 opening: artifacts ready. Please confirm.", "tool_calls": []},
        # S2 opening: write s2_data_requirement.md
        {
            "content": "Writing S2 artifact.",
            "tool_calls": [
                _wa_call("c3", ".anappt/s2_data_requirement.md", _RESUME_S2_MD),
            ],
        },
        {"content": "S2 opening: ready. Please confirm.", "tool_calls": []},
    ]
    mock.chat_with_tools.side_effect = responses
    mock.chat.side_effect = ["session summary", "NO_UPDATE"]
    return mock


@pytest.fixture
def _force_zh():
    """Force zh locale for conversation tests."""
    i18n._reset_cache()
    i18n.set_locale("zh")
    yield
    i18n._reset_cache()


class TestResumeConversation:
    """Conversation-driven resume integration tests (Task E2.2).

    Tests that ``ConversationRunner`` can resume from a persisted state
    (S1 completed, S2 in_progress) and drive the pipeline to completion,
    and that a project without ``report.yaml`` can still run.
    """

    def test_resume_from_s2_in_progress_via_run(
        self,
        integration_project: Path,
        _force_zh: None,
    ) -> None:
        """Resume from S2 in_progress: a fresh ConversationRunner loads
        state from disk and continues the conversation from S2.

        Flow:
        1. Manually set state: S1 completed, S2 in_progress (simulating
           a prior session that exited mid-S2)
        2. Write S1 artifacts so state is consistent
        3. Create new ConversationRunner with fresh StateManager (loads
           from state.yaml on disk)
        4. run() enters S2 (already in_progress, no transition), produces
           opening; user confirms S2-S6
        5. Verify pipeline completes and all artifacts exist
        """
        project_dir = integration_project

        # --- Phase 1: Manually set state to S1 completed, S2 in_progress ---
        state = StateManager(project_dir / ".anappt" / "state.yaml")
        state.transition("S1", StageStatus.IN_PROGRESS)
        state.transition("S1", StageStatus.AWAITING_REVIEW)
        state.transition("S1", StageStatus.COMPLETED)
        state.transition("S2", StageStatus.IN_PROGRESS)
        state.save()

        # Write S1 artifacts (so state is consistent with disk)
        (project_dir / "report.yaml").write_text(
            _RESUME_REPORT_YAML, encoding="utf-8"
        )
        (project_dir / ".anappt" / "s1_topic.md").write_text(
            _RESUME_S1_TOPIC_MD, encoding="utf-8"
        )

        # --- Phase 2: Create new ConversationRunner with fresh state ---
        llm = _make_resume_llm_from_s2()
        # 5 confirms advance S2-S6; pipeline completes after S6 confirm
        ui = _FakeUI(inputs=["confirm"] * 5)
        ctx = _build_conv_ctx(project_dir, llm, ui)

        # Verify state was loaded from disk
        assert ctx.state.get_stage("S1").status == StageStatus.COMPLETED
        assert ctx.state.get_stage("S2").status == StageStatus.IN_PROGRESS
        assert ctx.state.state.current_stage == "S2"

        with patch("anappt.bridge.dashi_ppt.DashiPPTBridge") as mock_bridge:
            mock_bridge.render_deck.side_effect = _make_fake_render_deck(project_dir)
            ConversationRunner(ctx, mode="run", ui=ui).run()

        # --- Phase 3: Verify pipeline completed ---
        assert ctx.state.is_pipeline_complete()
        for stage in ctx.state.get_all_stages():
            assert stage.status == StageStatus.COMPLETED, (
                f"Stage {stage.id} should be completed, got {stage.status}"
            )

        # Verify S2-S6 artifacts exist
        assert (project_dir / ".anappt" / "s2_data_requirement.md").exists()
        assert (project_dir / ".anappt" / "s3_data_profile.md").exists()
        assert (project_dir / ".anappt" / "s4_analysis_report.md").exists()
        assert (project_dir / "output" / "final_report.md").exists()
        assert (project_dir / "output" / "ppt" / "goal.json").exists()
        assert (project_dir / "output" / "ppt" / "presentation.html").exists()

        # 10 chat_with_tools calls (2 per stage × 5 stages S2-S6)
        assert llm.chat_with_tools.call_count == 10

    def test_run_without_report_yaml(
        self,
        integration_project: Path,
        _force_zh: None,
    ) -> None:
        """A project without report.yaml can still run via ConversationRunner.

        Flow:
        1. Create project (has report.yaml from template)
        2. Delete report.yaml
        3. Build context with empty ReportConfig (since report.yaml is gone)
        4. ConversationRunner run() enters S1 without raising FileNotFoundError
        5. Mock LLM writes report.yaml + s1_topic.md via write_artifact
        6. User confirms S1 → S2, then exits
        7. Verify report.yaml was generated and no exception was raised
        """
        project_dir = integration_project

        # Delete report.yaml to simulate a project without it
        report_yaml_path = project_dir / "report.yaml"
        assert report_yaml_path.exists(), "report.yaml should exist after init"
        report_yaml_path.unlink()
        assert not report_yaml_path.exists()

        # Build context with empty ReportConfig (no report.yaml to load)
        llm = _make_s1_only_llm()
        # confirm S1 → S2, then exit
        ui = _FakeUI(inputs=["confirm", "exit"])
        ctx = _build_conv_ctx(
            project_dir, llm, ui, config=ReportConfig()
        )

        with patch("anappt.bridge.dashi_ppt.DashiPPTBridge"):
            # Should not raise FileNotFoundError
            ConversationRunner(ctx, mode="run", ui=ui).run()

        # Verify report.yaml was generated by the LLM
        assert report_yaml_path.exists(), (
            "report.yaml should have been generated by the LLM"
        )
        with open(report_yaml_path, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
        assert yaml_data is not None
        assert yaml_data["report"]["topic"]
        assert yaml_data["report"]["motivation"]
        assert yaml_data["report"]["objectives"]

        # Verify s1_topic.md was generated
        assert (project_dir / ".anappt" / "s1_topic.md").exists()

        # Verify S1 was confirmed (S1 completed, S2 entered)
        assert ctx.state.get_stage("S1").status == StageStatus.COMPLETED
        assert ctx.state.state.current_stage == "S2"

        # 4 chat_with_tools calls (S1: 2 + S2: 2)
        assert llm.chat_with_tools.call_count == 4
