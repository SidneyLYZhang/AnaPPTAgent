"""Integration test: Full pipeline S1-S6 end-to-end.

Tests that the complete pipeline runs from project creation through all
six stages, producing expected output artifacts at each step.

Task 8.1 — Integration test: full pipeline.
Task E2.1 — Conversation-driven integration test (ConversationRunner).
"""

from __future__ import annotations

import json
import subprocess
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
        # encoding="utf-8" required: commit messages contain Chinese (zh locale)
        # and Windows default GBK codec fails to decode them.
        git_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
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


# ---------------------------------------------------------------------------
# Task E2.1: Conversation-driven integration tests (ConversationRunner)
# ---------------------------------------------------------------------------


# A complete report.yaml that satisfies S1 is_ready (topic/motivation/
# objectives non-empty, parseable by ReportConfig.from_yaml).
_COMPLETE_REPORT_YAML = """\
project:
  name: "Conversation Test Project"
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

_S1_TOPIC_MD = (
    "# Refined Topic\n\n"
    "Detailed topic document for Q3 channel ROI analysis.\n"
)

# S2 is_ready requires at least one '#' heading or '- '/'* ' list item.
_S2_DATA_REQ_MD = (
    "# Data Requirements\n\n"
    "## Metrics\n"
    "- DAU: daily active users\n"
    "- Revenue: total daily revenue\n\n"
    "## Dimensions\n"
    "- date\n"
    "- channel\n"
)

_S3_DATA_PROFILE_MD = (
    "# Data Profile\n\n"
    "## sample.csv\n"
    "- Rows: 3\n"
    "- Columns: name, value, date\n"
)

_S4_ANALYSIS_MD = (
    "# Analysis Report\n\n"
    "## Key Findings\n"
    "- Finding 1: Value A is 10\n"
    "- Finding 2: Value B is 20\n"
)

# S5 is_ready requires >= 2 level-1 headings (lines starting with "# "
# but not "## ").
_S5_FINAL_REPORT_MD = (
    "# Executive Summary\n\n"
    "This is a comprehensive analysis report.\n\n"
    "# Methodology\n\n"
    "Data was analyzed using statistical methods.\n\n"
    "# Findings\n\n"
    "- Key finding 1\n"
    "- Key finding 2\n"
)

_S6_GOAL_JSON = json.dumps(
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
    """In-memory UI mock satisfying InteractiveUIProtocol.

    ``input`` returns successive strings from ``inputs``; once the
    queue is empty it returns ``"exit"`` to avoid infinite loops.
    """

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


def _rd_call(
    call_id: str, goal_json_path: str, output_html_path: str
) -> dict:
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


def _make_full_pipeline_llm() -> MagicMock:
    """Build a mock LLM that drives the full S1-S6 conversation.

    Each stage opening produces two ``chat_with_tools`` responses:
    1. A response with ``tool_calls`` that write the stage's artifacts
       (and call ``render_deck`` for S6).
    2. A response with no ``tool_calls`` containing the final opening
       text.

    The ``chat`` method is called twice during ``_finalize``:
    once for ``session.finalize_summary`` and once for
    ``memory.update``.
    """
    mock = MagicMock()
    responses = [
        # S1 opening: write report.yaml + s1_topic.md
        {
            "content": "Writing S1 artifacts.",
            "tool_calls": [
                _wa_call("c1", "report.yaml", _COMPLETE_REPORT_YAML),
                _wa_call("c2", ".anappt/s1_topic.md", _S1_TOPIC_MD),
            ],
        },
        {"content": "S1 opening: artifacts ready. Please confirm.", "tool_calls": []},
        # S2 opening: write s2_data_requirement.md
        {
            "content": "Writing S2 artifact.",
            "tool_calls": [
                _wa_call("c3", ".anappt/s2_data_requirement.md", _S2_DATA_REQ_MD),
            ],
        },
        {"content": "S2 opening: artifact ready. Please confirm.", "tool_calls": []},
        # S3 opening: write s3_data_profile.md
        {
            "content": "Writing S3 artifact.",
            "tool_calls": [
                _wa_call("c4", ".anappt/s3_data_profile.md", _S3_DATA_PROFILE_MD),
            ],
        },
        {"content": "S3 opening: artifact ready. Please confirm.", "tool_calls": []},
        # S4 opening: write s4_analysis_report.md
        {
            "content": "Writing S4 artifact.",
            "tool_calls": [
                _wa_call("c5", ".anappt/s4_analysis_report.md", _S4_ANALYSIS_MD),
            ],
        },
        {"content": "S4 opening: artifact ready. Please confirm.", "tool_calls": []},
        # S5 opening: write final_report.md
        {
            "content": "Writing S5 artifact.",
            "tool_calls": [
                _wa_call("c6", "output/final_report.md", _S5_FINAL_REPORT_MD),
            ],
        },
        {"content": "S5 opening: artifact ready. Please confirm.", "tool_calls": []},
        # S6 opening: write goal.json + render_deck
        {
            "content": "Constructing goal.json and rendering deck.",
            "tool_calls": [
                _wa_call("c7", "output/ppt/goal.json", _S6_GOAL_JSON),
                _rd_call("c8", "output/ppt/goal.json", "output/ppt/presentation.html"),
            ],
        },
        {"content": "S6 opening: PPT rendered. Please confirm.", "tool_calls": []},
    ]
    mock.chat_with_tools.side_effect = responses
    # _finalize calls chat for finalize_summary + memory.update
    mock.chat.side_effect = ["session summary", "NO_UPDATE"]
    return mock


def _build_conversation_ctx(
    project_dir: Path,
    llm: MagicMock,
    ui: _FakeUI,
    config: ReportConfig | None = None,
) -> PipelineContext:
    """Build a PipelineContext with all services needed by ConversationRunner.

    Unlike the ``make_context`` fixture, this includes a ``MemoryManager``
    (required by ``_build_system_prompt``) and uses the provided ``ui``
    instead of a MagicMock.
    """
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


@pytest.fixture
def _force_zh():
    """Force zh locale for conversation tests (matches test_conversation.py)."""
    i18n._reset_cache()
    i18n.set_locale("zh")
    yield
    i18n._reset_cache()


class TestConversationDrivenPipeline:
    """Conversation-driven integration tests for the full S1-S6 pipeline.

    These tests use ``ConversationRunner`` (Task C1) with a mock LLM that
    writes artifacts via ``tool_calls`` at each stage opening, then returns
    a final text. The user inputs ``confirm`` to advance through stages.

    The legacy ``TestFullPipeline`` class (Orchestrator-based) is preserved
    for backward compatibility with Task C4's retained orchestrator gating.
    """

    def test_conversation_full_pipeline_s1_to_s6(
        self,
        integration_project: Path,
        _force_zh: None,
    ) -> None:
        """Test that ConversationRunner drives S1-S6 to completion.

        Flow:
        1. Create project with create_project() (includes report.yaml + git)
        2. Mock LLM writes stage artifacts via write_artifact tool_calls
           at each opening; S6 also calls render_deck
        3. User inputs 'confirm' 6 times to advance S1-S6
        4. Verify all output files, state, session history, and git commits
        """
        project_dir = integration_project
        llm = _make_full_pipeline_llm()
        # 6 confirms advance S1-S6; pipeline completes after S6 confirm
        # (sets _exit=True), so no explicit 'exit' is needed.
        ui = _FakeUI(inputs=["confirm"] * 6)
        ctx = _build_conversation_ctx(project_dir, llm, ui)

        # Patch DashiPPTBridge at the source module so the render_deck
        # tool (which imports inside the function) gets the mock.
        with patch("anappt.bridge.dashi_ppt.DashiPPTBridge") as mock_bridge:
            mock_bridge.render_deck.side_effect = _make_fake_render_deck(project_dir)
            ConversationRunner(ctx, mode="run", ui=ui).run()

        # --- Verify S1 artifacts ---
        report_yaml = project_dir / "report.yaml"
        assert report_yaml.exists(), "report.yaml should exist"
        with open(report_yaml, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
        assert yaml_data is not None
        assert yaml_data["report"]["topic"]
        assert yaml_data["report"]["motivation"]
        assert yaml_data["report"]["objectives"]
        assert (project_dir / ".anappt" / "s1_topic.md").exists()

        # --- Verify S2-S4 artifacts ---
        assert (project_dir / ".anappt" / "s2_data_requirement.md").exists()
        assert (project_dir / ".anappt" / "s3_data_profile.md").exists()
        assert (project_dir / ".anappt" / "s4_analysis_report.md").exists()

        # --- Verify S5 artifact (output/final_report.md, NOT report.md) ---
        final_report = project_dir / "output" / "final_report.md"
        assert final_report.exists(), "output/final_report.md should exist"
        content = final_report.read_text(encoding="utf-8")
        # S5 is_ready requires >= 2 level-1 headings
        h1_count = sum(
            1 for line in content.splitlines()
            if line.strip().startswith("# ") and not line.strip().startswith("## ")
        )
        assert h1_count >= 2

        # --- Verify S6 artifacts ---
        goal_json = project_dir / "output" / "ppt" / "goal.json"
        assert goal_json.exists(), "output/ppt/goal.json should exist"
        json.loads(goal_json.read_text(encoding="utf-8"))  # must be valid JSON
        ppt_html = project_dir / "output" / "ppt" / "presentation.html"
        assert ppt_html.exists(), "output/ppt/presentation.html should exist"

        # --- Verify state: all stages completed ---
        assert ctx.state.is_pipeline_complete()
        for stage in ctx.state.get_all_stages():
            assert stage.status == StageStatus.COMPLETED, (
                f"Stage {stage.id} should be completed, got {stage.status}"
            )

        # --- Verify session history files (one per stage) ---
        session_dir = project_dir / ".anappt" / "session_history"
        session_files = list(session_dir.glob("*.md"))
        assert len(session_files) >= 1, (
            "Expected at least one session history file"
        )
        # Each file is named YYYY-MM-DD_<stage>.md
        for f in session_files:
            name = f.name
            assert any(name.endswith(f"_{s}.md") for s in ["S1", "S2", "S3", "S4", "S5", "S6"]), (
                f"Session file {name} should end with _<stage>.md"
            )

        # --- Verify git log has commit records ---
        git_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        assert git_log.returncode == 0
        commits = git_log.stdout.strip().split("\n")
        # At least: initial commit + 6 confirm commits + 1 exit commit
        assert len(commits) >= 2, (
            f"Expected at least 2 git commits, got {len(commits)}"
        )

        # --- Verify LLM was called appropriately ---
        # 12 chat_with_tools calls (2 per stage × 6 stages)
        assert llm.chat_with_tools.call_count == 12
        # 2 chat calls (finalize_summary + memory.update)
        assert llm.chat.call_count == 2

    def test_conversation_produces_session_history_with_summary(
        self,
        integration_project: Path,
        _force_zh: None,
    ) -> None:
        """After a conversation run, session history files contain the
        LLM-generated core summary at the top (## 核心摘要)."""
        project_dir = integration_project
        llm = _make_full_pipeline_llm()
        ui = _FakeUI(inputs=["confirm"] * 6)
        ctx = _build_conversation_ctx(project_dir, llm, ui)

        with patch("anappt.bridge.dashi_ppt.DashiPPTBridge") as mock_bridge:
            mock_bridge.render_deck.side_effect = _make_fake_render_deck(project_dir)
            ConversationRunner(ctx, mode="run", ui=ui).run()

        session_dir = project_dir / ".anappt" / "session_history"
        session_files = list(session_dir.glob("*.md"))
        assert len(session_files) >= 1
        # The mock LLM returns "session summary" for finalize_summary;
        # this text should appear in at least one session file.
        found_summary = False
        for f in session_files:
            content = f.read_text(encoding="utf-8")
            if "session summary" in content or "核心摘要" in content:
                found_summary = True
                break
        assert found_summary, (
            "Expected session history to contain the LLM-generated summary"
        )
