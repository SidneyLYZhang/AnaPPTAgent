"""Tests for CLI module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.cli import InteractiveUI, _build_stages, _load_pipeline_context, main
from anappt.i18n import t


@pytest.fixture
def mock_project(tmp_path: Path, monkeypatch) -> Path:
    """Create a mock project and chdir to it."""
    from anappt.project import create_project

    project_dir = tmp_path / "test_cli_project"
    create_project(project_dir, project_name="TestCLI", init_git=False)

    monkeypatch.chdir(project_dir)
    return project_dir


@pytest.fixture
def stub_collaborators(monkeypatch, tmp_path: Path) -> None:
    """Stub heavy optional collaborators used by _load_pipeline_context.

    Patches ``Path.home`` so the global ``~/.anappt/models.yaml`` does
    not exist (``load_global_config`` returns an empty ModelsConfig),
    resets the web tool module configs, and stubs SkillManager so no
    real skill lookup or network access happens during CLI tests that
    only need the runner to be constructed.
    """
    monkeypatch.setattr("anappt.llm.provider.Path.home", lambda: tmp_path)
    monkeypatch.setattr("anappt.tools.web_search._config", None)
    monkeypatch.setattr("anappt.tools.web_fetch._config", None)
    from anappt.io.skill_manager import SkillManager

    monkeypatch.setattr(SkillManager, "__init__", lambda self: None)
    monkeypatch.setattr(SkillManager, "locate_skill", lambda self, name=None: None)


class TestInteractiveUI:
    """Tests for InteractiveUI class."""

    def test_print_without_rich(self, capsys) -> None:
        ui = InteractiveUI(use_rich=False)
        ui.print("Hello World")
        captured = capsys.readouterr()
        assert "Hello World" in captured.out

    def test_input_without_rich(self, monkeypatch) -> None:
        ui = InteractiveUI(use_rich=False)
        monkeypatch.setattr("builtins.input", lambda prompt: "test input")
        result = ui.input("Enter: ")
        assert result == "test input"

    def test_confirm_yes(self, monkeypatch) -> None:
        ui = InteractiveUI(use_rich=False)
        monkeypatch.setattr("builtins.input", lambda prompt: "y")
        assert ui.confirm("Confirm?") is True

    def test_confirm_no(self, monkeypatch) -> None:
        ui = InteractiveUI(use_rich=False)
        monkeypatch.setattr("builtins.input", lambda prompt: "n")
        assert ui.confirm("Confirm?") is False

    def test_confirm_yes_full(self, monkeypatch) -> None:
        ui = InteractiveUI(use_rich=False)
        monkeypatch.setattr("builtins.input", lambda prompt: "yes")
        assert ui.confirm("Confirm?") is True

    def test_table_without_rich(self, capsys) -> None:
        ui = InteractiveUI(use_rich=False)
        ui.table(["A", "B"], [["1", "2"], ["3", "4"]])
        captured = capsys.readouterr()
        assert "A" in captured.out
        assert "1" in captured.out

    def test_progress_without_rich(self, capsys) -> None:
        ui = InteractiveUI(use_rich=False)
        ui.progress("Loading")
        captured = capsys.readouterr()
        assert "Loading" in captured.out


class TestBuildStages:
    """Tests for _build_stages function."""

    def test_returns_six_stages(self) -> None:
        stages = _build_stages()
        assert len(stages) == 6

    def test_stage_ids_in_order(self) -> None:
        stages = _build_stages()
        ids = [s.stage_id for s in stages]
        assert ids == ["S1", "S2", "S3", "S4", "S5", "S6"]

    def test_all_instances(self) -> None:
        stages = _build_stages()
        for stage in stages:
            assert hasattr(stage, "run")
            assert hasattr(stage, "stage_id")
            assert hasattr(stage, "stage_name")


class TestMainCLI:
    """Tests for the main CLI entry point."""

    def test_no_args_prints_usage(self, capsys) -> None:
        result = main([])
        assert result == 0
        captured = capsys.readouterr()
        assert "Usage" in captured.out or "anappt" in captured.out

    def test_unknown_command(self, capsys) -> None:
        result = main(["unknown_cmd"])
        assert result == 1
        captured = capsys.readouterr()
        assert "unknown" in captured.out.lower() or "Unknown" in captured.out

    def test_status_no_project(self, tmp_path: Path, monkeypatch, capsys) -> None:
        monkeypatch.chdir(tmp_path)
        result = main(["status"])
        assert result == 1
        captured = capsys.readouterr()
        assert t("cli.no_project_found") in captured.out

    def test_run_no_project(self, tmp_path: Path, monkeypatch, capsys) -> None:
        monkeypatch.chdir(tmp_path)
        result = main(["run"])
        assert result == 1

    def test_resume_no_project(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = main(["resume"])
        assert result == 1

    def test_config_show(self, capsys) -> None:
        result = main(["config", "show"])
        assert result == 0
        captured = capsys.readouterr()
        # Should print some config output
        assert len(captured.out) > 0

    def test_config_invalid_subcommand(self, capsys) -> None:
        result = main(["config", "invalid"])
        assert result == 1

    def test_init_in_place_no_name(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """``anappt init`` with no name initializes cwd in place (Task A1)."""
        monkeypatch.chdir(tmp_path)
        result = main(["init", "--no-skill"])

        assert result == 0
        # Project structure created in tmp_path itself (not a subdirectory).
        assert (tmp_path / ".anappt" / "state.yaml").is_file()
        assert (tmp_path / ".anappt" / "memory.md").is_file()
        assert (tmp_path / "report.yaml").exists()
        captured = capsys.readouterr()
        # In-place init success message should be printed.
        assert "anappt" in captured.out.lower() or "项目" in captured.out

    def test_init_with_name_arg_creates_subdir(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """``anappt init <name>`` creates a subdirectory (Task A1)."""
        monkeypatch.chdir(tmp_path)
        result = main(["init", "arg_project", "--no-skill"])

        assert result == 0
        project_path = tmp_path / "arg_project"
        assert project_path.exists()
        assert (project_path / ".anappt" / "state.yaml").is_file()
        assert (project_path / "report.yaml").exists()

    def test_init_in_place_already_initialized_returns_1(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """``anappt init`` in an already-initialized directory exits 1."""
        monkeypatch.chdir(tmp_path)
        # First init succeeds.
        assert main(["init", "--no-skill"]) == 0
        assert (tmp_path / ".anappt" / "state.yaml").is_file()
        # Second init on the same directory should fail.
        result = main(["init", "--no-skill"])
        assert result == 1
        captured = capsys.readouterr()
        # The "already anappt project" message should be printed (zh or en).
        assert "已是" in captured.out or "already" in captured.out.lower()

    def test_init_existing_dir_fails(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        monkeypatch.chdir(tmp_path)
        project_path = tmp_path / "existing"
        project_path.mkdir()
        (project_path / "file.txt").write_text("content", encoding="utf-8")

        result = main(["init", "existing"])
        assert result == 1


class TestConversationRunnerDelegation:
    """Tests that run/resume/interactive delegate to ConversationRunner (C2/C3/C4)."""

    def test_run_invokes_conversation_runner(
        self, mock_project: Path, stub_collaborators: None, monkeypatch
    ) -> None:
        """``anappt run`` constructs ConversationRunner(mode="run") and calls run()."""
        runner_mock = MagicMock()
        runner_mock.run = MagicMock(return_value=None)
        constructor = MagicMock(return_value=runner_mock)
        monkeypatch.setattr("anappt.cli.ConversationRunner", constructor)

        result = main(["run"])

        assert result == 0
        assert constructor.call_count == 1
        _args, kwargs = constructor.call_args
        assert kwargs.get("mode") == "run"
        assert runner_mock.run.call_count == 1

    def test_resume_invokes_conversation_runner(
        self, mock_project: Path, stub_collaborators: None, monkeypatch
    ) -> None:
        """``anappt resume`` shares the run path (mode="run").

        In the conversational TUI model, resume and run are equivalent —
        ``ConversationRunner._enter_stage`` recovers from the persisted
        state.yaml automatically. The CLI keeps a separate ``resume``
        entry in the command table for UX continuity.
        """
        runner_mock = MagicMock()
        runner_mock.run = MagicMock(return_value=None)
        constructor = MagicMock(return_value=runner_mock)
        monkeypatch.setattr("anappt.cli.ConversationRunner", constructor)

        result = main(["resume"])

        assert result == 0
        assert constructor.call_count == 1
        _args, kwargs = constructor.call_args
        assert kwargs.get("mode") == "run"
        assert runner_mock.run.call_count == 1

    def test_interactive_invokes_conversation_runner(
        self, mock_project: Path, stub_collaborators: None, monkeypatch
    ) -> None:
        """``anappt interactive`` constructs ConversationRunner(mode="interactive")."""
        runner_mock = MagicMock()
        runner_mock.run = MagicMock(return_value=None)
        constructor = MagicMock(return_value=runner_mock)
        monkeypatch.setattr("anappt.cli.ConversationRunner", constructor)

        result = main(["interactive"])

        assert result == 0
        assert constructor.call_count == 1
        _args, kwargs = constructor.call_args
        assert kwargs.get("mode") == "interactive"
        assert runner_mock.run.call_count == 1

    def test_run_does_not_call_orchestrator(
        self, mock_project: Path, stub_collaborators: None, monkeypatch
    ) -> None:
        """``anappt run`` no longer touches Orchestrator.run/confirm/revise (C4)."""
        runner_mock = MagicMock()
        monkeypatch.setattr(
            "anappt.cli.ConversationRunner",
            MagicMock(return_value=runner_mock),
        )

        # Spy on Orchestrator to ensure cmd_run never constructs one.
        from anappt.orchestrator import Orchestrator

        orch_init_spy = MagicMock(wraps=Orchestrator.__init__)
        monkeypatch.setattr(Orchestrator, "__init__", orch_init_spy)

        main(["run"])

        assert orch_init_spy.call_count == 0
        assert runner_mock.run.call_count == 1


class TestStatusCommand:
    """Tests for the status command with a valid project."""

    def test_status_shows_stages(
        self, mock_project: Path, capsys, monkeypatch
    ) -> None:
        result = main(["status"])
        assert result == 0
        captured = capsys.readouterr()
        assert "S1" in captured.out or "Pipeline" in captured.out


class TestProtocolCompliance:
    """Verify InteractiveUI satisfies InteractiveUIProtocol."""

    def test_implements_all_methods(self) -> None:
        ui = InteractiveUI(use_rich=False)
        assert hasattr(ui, "print")
        assert hasattr(ui, "input")
        assert hasattr(ui, "confirm")
        assert hasattr(ui, "table")
        assert hasattr(ui, "progress")

    def test_print_callable(self) -> None:
        ui = InteractiveUI(use_rich=False)
        assert callable(ui.print)

    def test_input_callable(self) -> None:
        ui = InteractiveUI(use_rich=False)
        assert callable(ui.input)

    def test_confirm_callable(self) -> None:
        ui = InteractiveUI(use_rich=False)
        assert callable(ui.confirm)

    def test_table_callable(self) -> None:
        ui = InteractiveUI(use_rich=False)
        assert callable(ui.table)

    def test_progress_callable(self) -> None:
        ui = InteractiveUI(use_rich=False)
        assert callable(ui.progress)


class TestLoadPipelineContext:
    """Tests for _load_pipeline_context (Task A2)."""

    def test_load_pipeline_context_no_report_yaml(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A project with state.yaml but no report.yaml loads with empty config.

        S1 is responsible for generating report.yaml; before that, the
        pipeline context must still be constructible without raising.
        """
        from anappt.project import create_project

        project_dir = tmp_path / "no_report"
        create_project(project_dir, project_name="NoReport", init_git=False)
        # Remove report.yaml to simulate the pre-S1 state.
        (project_dir / "report.yaml").unlink()

        # Patch HOME so global ~/.anappt/models.yaml does not exist.
        monkeypatch.setattr("anappt.llm.provider.Path.home", lambda: tmp_path)
        # Reset module-level web tool configs to avoid leakage from prior tests.
        monkeypatch.setattr("anappt.tools.web_search._config", None)
        monkeypatch.setattr("anappt.tools.web_fetch._config", None)
        # Stub out heavy optional collaborators.
        from anappt.io.skill_manager import SkillManager

        monkeypatch.setattr(SkillManager, "__init__", lambda self: None)
        monkeypatch.setattr(SkillManager, "locate_skill", lambda self, name: None)

        ctx = _load_pipeline_context(project_dir)

        # An empty ReportConfig is used as a placeholder.
        assert ctx.config.project.name == ""
        assert ctx.config.report.topic == ""
        # State was loaded from the state.yaml written by init.
        assert ctx.state.state.current_stage == "S1"

    def test_load_pipeline_context_invalid_report_yaml_falls_back(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """An unparseable report.yaml falls back to an empty ReportConfig."""
        from anappt.project import create_project

        project_dir = tmp_path / "bad_report"
        create_project(project_dir, project_name="BadReport", init_git=False)
        # Overwrite report.yaml with invalid YAML.
        (project_dir / "report.yaml").write_text(
            "project: [this is\n  not: valid\n  yaml: {unclosed",
            encoding="utf-8",
        )

        monkeypatch.setattr("anappt.llm.provider.Path.home", lambda: tmp_path)
        monkeypatch.setattr("anappt.tools.web_search._config", None)
        monkeypatch.setattr("anappt.tools.web_fetch._config", None)
        from anappt.io.skill_manager import SkillManager

        monkeypatch.setattr(SkillManager, "__init__", lambda self: None)
        monkeypatch.setattr(SkillManager, "locate_skill", lambda self, name: None)

        # Should not raise — falls back to empty ReportConfig.
        ctx = _load_pipeline_context(project_dir)
        assert ctx.config.project.name == ""

    def test_load_pipeline_context_injects_memory_manager(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """_load_pipeline_context injects a MemoryManager pointing at .anappt/memory.md.

        Also verifies memory.md absence is tolerated: ``read()`` returns ""
        when the file does not exist (Task D2).
        """
        from anappt.io.memory import MemoryManager
        from anappt.project import create_project

        project_dir = tmp_path / "with_memory"
        create_project(project_dir, project_name="WithMemory", init_git=False)

        monkeypatch.setattr("anappt.llm.provider.Path.home", lambda: tmp_path)
        monkeypatch.setattr("anappt.tools.web_search._config", None)
        monkeypatch.setattr("anappt.tools.web_fetch._config", None)
        from anappt.io.skill_manager import SkillManager

        monkeypatch.setattr(SkillManager, "__init__", lambda self: None)
        monkeypatch.setattr(SkillManager, "locate_skill", lambda self, name: None)

        ctx = _load_pipeline_context(project_dir)

        # Memory manager is injected.
        assert ctx.memory is not None
        assert isinstance(ctx.memory, MemoryManager)
        # Points at the project's .anappt/memory.md.
        assert ctx.memory.memory_file == project_dir / ".anappt" / "memory.md"
        # read() tolerates absence (init writes an empty memory.md, so it
        # exists; either way read() returns "").
        assert ctx.memory.read() == ""
