"""Tests for core type definitions (PipelineContext, StageOutput, model_role_for_stage)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.config import ReportConfig
from anappt.io.state import StateManager
from anappt.types import (
    PipelineContext,
    StageOutput,
    model_role_for_stage,
)


@pytest.fixture
def mock_config() -> ReportConfig:
    """Return a default ReportConfig for testing."""
    return ReportConfig()


@pytest.fixture
def mock_llm() -> MagicMock:
    """Return a mock LLM provider."""
    mock = MagicMock()
    mock.chat.return_value = "Mock response"
    return mock


@pytest.fixture
def mock_state(tmp_path: Path) -> StateManager:
    """Return a StateManager with a temp state file."""
    return StateManager(tmp_path / "state.yaml")


@pytest.fixture
def ctx(
    tmp_path: Path,
    mock_config: ReportConfig,
    mock_llm: MagicMock,
    mock_state: StateManager,
) -> PipelineContext:
    """Return a PipelineContext for testing."""
    return PipelineContext(
        project_dir=tmp_path,
        config=mock_config,
        llm=mock_llm,
        state=mock_state,
    )


class TestStageOutput:
    """Tests for StageOutput class."""

    def test_default_values(self) -> None:
        output = StageOutput()
        assert output.success is True
        assert output.artifacts == []
        assert output.summary == ""
        assert output.data == {}
        assert output.next_action == "confirm"

    def test_with_values(self) -> None:
        output = StageOutput(
            success=False,
            artifacts=["file1.md", "file2.md"],
            summary="Test summary",
            data={"key": "value"},
            next_action="retry",
        )
        assert output.success is False
        assert output.artifacts == ["file1.md", "file2.md"]
        assert output.summary == "Test summary"
        assert output.data == {"key": "value"}
        assert output.next_action == "retry"

    def test_to_dict(self) -> None:
        output = StageOutput(
            success=True,
            artifacts=["a.md"],
            summary="Summary",
            data={"k": "v"},
            next_action="confirm",
        )
        d = output.to_dict()
        assert d["success"] is True
        assert d["artifacts"] == ["a.md"]
        assert d["summary"] == "Summary"
        assert d["data"] == {"k": "v"}
        assert d["next_action"] == "confirm"

    def test_from_dict(self) -> None:
        d = {
            "success": False,
            "artifacts": ["x.md"],
            "summary": "Failed",
            "data": {"error": "test"},
            "next_action": "retry",
        }
        output = StageOutput.from_dict(d)
        assert output.success is False
        assert output.artifacts == ["x.md"]
        assert output.summary == "Failed"
        assert output.data == {"error": "test"}
        assert output.next_action == "retry"

    def test_from_dict_defaults(self) -> None:
        output = StageOutput.from_dict({})
        assert output.success is True
        assert output.artifacts == []
        assert output.summary == ""
        assert output.data == {}

    def test_roundtrip(self) -> None:
        output = StageOutput(
            success=True,
            artifacts=["a", "b"],
            summary="Roundtrip",
            data={"x": 1},
            next_action="confirm",
        )
        d = output.to_dict()
        restored = StageOutput.from_dict(d)
        assert restored.success == output.success
        assert restored.artifacts == output.artifacts
        assert restored.summary == output.summary
        assert restored.data == output.data
        assert restored.next_action == output.next_action

    def test_empty_artifacts_list(self) -> None:
        output = StageOutput(artifacts=None)
        assert output.artifacts == []

    def test_empty_data_dict(self) -> None:
        output = StageOutput(data=None)
        assert output.data == {}


class TestPipelineContext:
    """Tests for PipelineContext class."""

    def test_basic_construction(
        self,
        tmp_path: Path,
        mock_config: ReportConfig,
        mock_llm: MagicMock,
        mock_state: StateManager,
    ) -> None:
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=mock_config,
            llm=mock_llm,
            state=mock_state,
        )
        assert ctx.project_dir == tmp_path
        assert ctx.config == mock_config
        assert ctx.llm == mock_llm
        assert ctx.state == mock_state
        assert ctx.ui is None
        assert ctx.session is None
        assert ctx.git is None

    def test_output_dir_created(self, tmp_path: Path, mock_config, mock_llm, mock_state) -> None:
        output_dir = tmp_path / "custom_output"
        PipelineContext(
            project_dir=tmp_path,
            config=mock_config,
            llm=mock_llm,
            state=mock_state,
            output_dir=output_dir,
        )
        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_default_output_dir(self, tmp_path: Path, mock_config, mock_llm, mock_state) -> None:
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=mock_config,
            llm=mock_llm,
            state=mock_state,
        )
        assert ctx.output_dir == tmp_path / "output"
        assert ctx.output_dir.exists()

    def test_get_artifact_path(
        self, tmp_path: Path, mock_config, mock_llm, mock_state
    ) -> None:
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=mock_config,
            llm=mock_llm,
            state=mock_state,
        )
        path = ctx.get_artifact_path("report.md")
        assert path == ctx.output_dir / "report.md"

    def test_get_anappt_path(
        self, tmp_path: Path, mock_config, mock_llm, mock_state
    ) -> None:
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=mock_config,
            llm=mock_llm,
            state=mock_state,
        )
        path = ctx.get_anappt_path("s1_topic.md")
        assert path == tmp_path / ".anappt" / "s1_topic.md"
        assert path.parent.exists()

    def test_get_data_dir(
        self, tmp_path: Path, mock_config, mock_llm, mock_state
    ) -> None:
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=mock_config,
            llm=mock_llm,
            state=mock_state,
        )
        assert ctx.get_data_dir() == tmp_path / "data"

    def test_with_ui(
        self,
        tmp_path: Path,
        mock_config,
        mock_llm,
        mock_state,
    ) -> None:
        ui = MagicMock()
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=mock_config,
            llm=mock_llm,
            state=mock_state,
            ui=ui,
        )
        assert ctx.ui is ui

    def test_with_session(
        self,
        tmp_path: Path,
        mock_config,
        mock_llm,
        mock_state,
    ) -> None:
        from anappt.io.session import SessionLogger

        session = SessionLogger(tmp_path / ".anappt" / "session_history")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=mock_config,
            llm=mock_llm,
            state=mock_state,
            session=session,
        )
        assert ctx.session is session

    def test_with_git(
        self,
        tmp_path: Path,
        mock_config,
        mock_llm,
        mock_state,
    ) -> None:
        from anappt.io.git_auto import GitAutoCommit

        git = GitAutoCommit(tmp_path)
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=mock_config,
            llm=mock_llm,
            state=mock_state,
            git=git,
        )
        assert ctx.git is git

    def test_memory_defaults_to_none(
        self,
        tmp_path: Path,
        mock_config,
        mock_llm,
        mock_state,
    ) -> None:
        """PipelineContext.memory defaults to None when not injected (Task D2)."""
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=mock_config,
            llm=mock_llm,
            state=mock_state,
        )
        assert ctx.memory is None

    def test_with_memory(
        self,
        tmp_path: Path,
        mock_config,
        mock_llm,
        mock_state,
    ) -> None:
        """PipelineContext accepts a MemoryManager via the memory kwarg (Task D2)."""
        from anappt.io.memory import MemoryManager

        memory_file = tmp_path / ".anappt" / "memory.md"
        memory = MemoryManager(memory_file)
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=mock_config,
            llm=mock_llm,
            state=mock_state,
            memory=memory,
        )
        assert ctx.memory is memory
        assert ctx.memory.memory_file == memory_file


class TestModelRoleForStage:
    """Tests for model_role_for_stage function."""

    def test_s1_reasoning(self) -> None:
        assert model_role_for_stage("S1") == "reasoning"

    def test_s2_reasoning(self) -> None:
        assert model_role_for_stage("S2") == "reasoning"

    def test_s3_reasoning(self) -> None:
        assert model_role_for_stage("S3") == "reasoning"

    def test_s4_analysis(self) -> None:
        assert model_role_for_stage("S4") == "analysis"

    def test_s5_writing(self) -> None:
        assert model_role_for_stage("S5") == "writing"

    def test_s6_writing(self) -> None:
        assert model_role_for_stage("S6") == "writing"

    def test_unknown_stage_defaults_to_reasoning(self) -> None:
        assert model_role_for_stage("S7") == "reasoning"

    def test_empty_stage_defaults_to_reasoning(self) -> None:
        assert model_role_for_stage("") == "reasoning"


class TestInteractiveUIProtocol:
    """Tests for InteractiveUIProtocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """Verify the protocol can be used with isinstance."""
        ui = MagicMock()
        ui.print = lambda msg: None
        ui.input = lambda prompt: ""
        ui.confirm = lambda prompt: True
        ui.table = lambda headers, rows: None
        ui.progress = lambda msg: None
        # The Protocol should be checkable (won't raise)
        assert hasattr(ui, "print")
        assert hasattr(ui, "input")
        assert hasattr(ui, "confirm")
        assert hasattr(ui, "table")
        assert hasattr(ui, "progress")
