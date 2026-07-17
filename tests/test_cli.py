"""Tests for CLI module."""

from __future__ import annotations

from pathlib import Path

import pytest

from anappt.cli import InteractiveUI, _build_stages, main


@pytest.fixture
def mock_project(tmp_path: Path, monkeypatch) -> Path:
    """Create a mock project and chdir to it."""
    from anappt.project import create_project

    project_dir = tmp_path / "test_cli_project"
    create_project(project_dir, project_name="TestCLI", init_git=False)

    monkeypatch.chdir(project_dir)
    return project_dir


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
        assert "No project" in captured.out or "no project" in captured.out.lower()

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

    def test_init_creates_project(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("builtins.input", lambda prompt: "my_test_project")
        result = main(["init"])

        assert result == 0
        project_path = tmp_path / "my_test_project"
        assert project_path.exists()
        assert (project_path / "report.yaml").exists()
        assert (project_path / ".anappt").is_dir()

    def test_init_with_name_arg(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = main(["init", "arg_project"])

        assert result == 0
        project_path = tmp_path / "arg_project"
        assert project_path.exists()

    def test_init_existing_dir_fails(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        monkeypatch.chdir(tmp_path)
        project_path = tmp_path / "existing"
        project_path.mkdir()
        (project_path / "file.txt").write_text("content", encoding="utf-8")

        result = main(["init", "existing"])
        assert result == 1


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
