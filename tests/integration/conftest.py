"""Shared fixtures for AnaPPTAgent integration tests.

Provides project creation, mock LLM, and context factory fixtures
for end-to-end and resume integration tests.
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.config import ReportConfig
from anappt.io.git_auto import GitAutoCommit
from anappt.io.session import SessionLogger
from anappt.io.state import StateManager
from anappt.project import create_project
from anappt.types import PipelineContext


@pytest.fixture
def integration_project(tmp_path: Path) -> Path:
    """Create a real project with create_project() and sample CSV data.

    Sets up git user config so GitAutoCommit commits work during tests.
    """
    project_dir = tmp_path / "integration_project"
    create_project(project_dir, project_name="Integration Test", init_git=True)

    # Configure git user for commits (required by GitAutoCommit)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Ensure initial commit exists (may have failed without user config)
    subprocess.run(
        ["git", "add", "."],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "chore: initialize project"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Add sample CSV data file for S3 (data loading)
    csv_path = project_dir / "data" / "sample.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "value", "date"])
        writer.writerow(["A", "10", "2026-01-01"])
        writer.writerow(["B", "20", "2026-02-01"])
        writer.writerow(["C", "30", "2026-03-01"])

    return project_dir


@pytest.fixture
def mock_llm_for_pipeline() -> MagicMock:
    """Create a mock LLM that returns role-appropriate canned responses.

    - reasoning role (S1, S2): returns a topic/requirement document with headings
    - analysis role (S4): chat_with_tools returns content with no tool calls
    - writing role (S5): returns a polished report with headings
    """
    mock = MagicMock()

    def chat_side_effect(role: str, messages: list, **kwargs: object) -> str:
        if role == "reasoning":
            return (
                "# Refined Topic\n\n"
                "## Analysis Objectives\n"
                "- Understand the data trends\n"
                "- Identify key patterns\n\n"
                "## Success Criteria\n"
                "- Clear findings with data support"
            )
        if role == "analysis":
            return "# Analysis Report\n\n## Key Findings\n\n- Finding 1\n- Finding 2"
        if role == "writing":
            return (
                "# Final Report\n\n"
                "## Executive Summary\n\n"
                "This is a comprehensive analysis report.\n\n"
                "## Methodology\n\n"
                "Data was analyzed using statistical methods.\n\n"
                "## Findings\n\n"
                "- Key finding 1\n"
                "- Key finding 2\n\n"
                "## Conclusions\n\n"
                "The analysis is complete."
            )
        return "Mock response"

    def chat_with_tools_side_effect(
        role: str, messages: list, tools: list, **kwargs: object
    ) -> dict:
        return {
            "content": (
                "# Analysis Report\n\n"
                "## Executive Summary\n\n"
                "Mock analysis from agent loop.\n\n"
                "## Key Findings\n\n"
                "- Finding 1\n"
                "- Finding 2"
            ),
            "tool_calls": [],
            "raw_response": MagicMock(),
        }

    mock.chat.side_effect = chat_side_effect
    mock.chat_with_tools.side_effect = chat_with_tools_side_effect
    return mock


@pytest.fixture
def make_context(
    integration_project: Path,
) -> object:
    """Factory fixture that creates PipelineContext instances.

    Each call creates a fresh StateManager (loads from state.yaml on disk),
    SessionLogger, GitAutoCommit, and mock UI.
    """
    project_dir = integration_project

    def _make(llm: object) -> PipelineContext:
        config = ReportConfig.from_yaml(project_dir / "report.yaml")
        config.delivery.theme_preference = "default"

        state = StateManager(project_dir / ".anappt" / "state.yaml")
        session = SessionLogger(project_dir / ".anappt" / "session_history")
        git = GitAutoCommit(project_dir)
        ui = MagicMock()

        return PipelineContext(
            project_dir=project_dir,
            config=config,
            llm=llm,
            state=state,
            ui=ui,
            session=session,
            git=git,
        )

    return _make


@pytest.fixture
def all_stages() -> list:
    """Create all 6 pipeline stage instances."""
    from anappt.stages.s1_topic import S1TopicStage
    from anappt.stages.s2_data_req import S2DataRequirementStage
    from anappt.stages.s3_data_load import S3DataLoadStage
    from anappt.stages.s4_analysis import S4AnalysisStage
    from anappt.stages.s5_report import S5ReportStage
    from anappt.stages.s6_ppt import S6PPTStage

    return [
        S1TopicStage(),
        S2DataRequirementStage(),
        S3DataLoadStage(),
        S4AnalysisStage(),
        S5ReportStage(),
        S6PPTStage(),
    ]


@pytest.fixture
def mock_ppt_bridge():
    """Patch DashiPPTBridge and return the mock class.

    The mock's generate_ppt creates a real HTML file at the expected path.
    Usage: use as a context manager.
    """
    from unittest.mock import patch

    class _MockBridgeContext:
        def __init__(self, project_dir: Path) -> None:
            self.project_dir = project_dir
            self.patcher = patch("anappt.stages.s6_ppt.DashiPPTBridge")
            self.mock_cls: MagicMock | None = None

        def __enter__(self) -> MagicMock:
            self.mock_cls = self.patcher.start()
            self.mock_cls.list_themes.return_value = {
                "default": "Default theme",
                "dark": "Dark theme",
            }
            mock_instance = self.mock_cls.return_value

            def fake_generate_ppt(
                markdown_content: str,
                theme: str | None = None,
                title: str = "Analysis Report",
                filename: str = "presentation.html",
            ) -> Path:
                ppt_dir = self.project_dir / "output" / "ppt"
                ppt_dir.mkdir(parents=True, exist_ok=True)
                html_path = ppt_dir / filename
                html_path.write_text(
                    "<!DOCTYPE html><html><body>Mock presentation</body></html>",
                    encoding="utf-8",
                )
                return html_path

            mock_instance.generate_ppt.side_effect = fake_generate_ppt
            return self.mock_cls

        def __exit__(self, *args: object) -> None:
            self.patcher.stop()

    return _MockBridgeContext
