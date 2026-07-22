"""Tests for project initialization."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from anappt.project import ProjectInitializer, create_project, is_anappt_project


@pytest.fixture
def templates_dir(tmp_path: Path) -> Path:
    """Create a minimal templates directory for testing."""
    tmpl_dir = tmp_path / "templates"
    (tmpl_dir / "data").mkdir(parents=True)

    # Create report.yaml.tmpl
    (tmpl_dir / "report.yaml.tmpl").write_text(
        'project:\n  name: ""\n  type: "one_time"\n',
        encoding="utf-8",
    )

    # Create .gitignore.tmpl
    (tmpl_dir / ".gitignore.tmpl").write_text(
        ".anappt/session_history/\n__pycache__/\n",
        encoding="utf-8",
    )

    # Create data/README.md.tmpl
    (tmpl_dir / "data" / "README.md.tmpl").write_text(
        "# Data Directory\n",
        encoding="utf-8",
    )

    return tmpl_dir


@pytest.fixture
def initializer(templates_dir: Path) -> ProjectInitializer:
    """Return a ProjectInitializer with test templates."""
    return ProjectInitializer(templates_dir=templates_dir)


class TestCreateProject:
    """Tests for create_project function."""

    def test_creates_directory_structure(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test_project"
        result = initializer.create_project(project_dir, init_git=False)

        assert result == project_dir
        assert project_dir.exists()
        assert (project_dir / "data").is_dir()
        assert (project_dir / "output").is_dir()
        assert (project_dir / "output" / "images").is_dir()
        assert (project_dir / ".anappt").is_dir()
        assert (project_dir / ".anappt" / "session_history").is_dir()

    def test_copies_templates(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test_project"
        initializer.create_project(project_dir, init_git=False)

        assert (project_dir / "report.yaml").exists()
        assert (project_dir / ".gitignore").exists()
        assert (project_dir / "data" / "README.md").exists()

    def test_report_yaml_content(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test_project"
        initializer.create_project(project_dir, project_name="MyProject", init_git=False)

        report_content = (project_dir / "report.yaml").read_text(encoding="utf-8")
        assert 'name: "MyProject"' in report_content

    def test_gitignore_content(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test_project"
        initializer.create_project(project_dir, init_git=False)

        gitignore_content = (project_dir / ".gitignore").read_text(encoding="utf-8")
        assert "session_history" in gitignore_content

    def test_existing_non_empty_dir_raises(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        (project_dir / "some_file.txt").write_text("content", encoding="utf-8")

        with pytest.raises(FileExistsError):
            initializer.create_project(project_dir, init_git=False)

    def test_existing_empty_dir_ok(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "empty"
        project_dir.mkdir()

        result = initializer.create_project(project_dir, init_git=False)
        assert result == project_dir

    def test_convenience_function(self, tmp_path: Path) -> None:
        """Test the create_project convenience function."""
        project_dir = tmp_path / "convenience_project"
        result = create_project(project_dir, project_name="Test", init_git=False)

        assert result == project_dir
        assert project_dir.exists()
        assert (project_dir / "report.yaml").exists()

    def test_nested_project_dir(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        """Should create nested directories."""
        project_dir = tmp_path / "a" / "b" / "c" / "project"
        result = initializer.create_project(project_dir, init_git=False)

        assert result.exists()


class TestCreateProjectInitMarkers:
    """Tests for the init markers written by create_project (Task A1)."""

    def test_writes_state_yaml(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        """create_project writes .anappt/state.yaml with all stages pending."""
        project_dir = tmp_path / "proj"
        initializer.create_project(
            project_dir, project_name="MarkerTest", init_git=False
        )

        state_file = project_dir / ".anappt" / "state.yaml"
        assert state_file.is_file(), "state.yaml should be written on init"

        with open(state_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data["project_name"] == "MarkerTest"
        assert data["current_stage"] == "S1"
        assert len(data["stages"]) == 6
        for stage in data["stages"]:
            assert stage["status"] == "pending"

    def test_writes_memory_md(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        """create_project writes an (empty) .anappt/memory.md."""
        project_dir = tmp_path / "proj"
        initializer.create_project(project_dir, init_git=False)

        memory_file = project_dir / ".anappt" / "memory.md"
        assert memory_file.is_file(), "memory.md should be written on init"
        # File may be empty or contain a placeholder; either is acceptable.
        assert memory_file.read_text(encoding="utf-8") == ""

    def test_state_yaml_makes_is_anappt_project_true(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        """After init, is_anappt_project returns True even without report.yaml."""
        project_dir = tmp_path / "proj"
        initializer.create_project(project_dir, init_git=False)

        # Delete report.yaml to simulate the pre-S1 state.
        (project_dir / "report.yaml").unlink()
        assert is_anappt_project(project_dir) is True


class TestInPlaceInit:
    """Tests for in-place initialization (Task A1)."""

    def test_in_place_empty_dir(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        """In-place init on an empty directory creates structure in place."""
        result = initializer.create_project(
            tmp_path, project_name="Empty", init_git=False, in_place=True
        )
        assert result == tmp_path
        assert (tmp_path / "data").is_dir()
        assert (tmp_path / ".anappt" / "state.yaml").is_file()
        assert (tmp_path / ".anappt" / "memory.md").is_file()
        assert (tmp_path / "report.yaml").exists()

    def test_in_place_non_empty_non_anappt_dir(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        """In-place init on a non-empty (non-anappt) directory succeeds.

        Existing files are preserved; anappt structure is created alongside.
        """
        pre_existing = tmp_path / "notes.txt"
        pre_existing.write_text("my notes", encoding="utf-8")
        pre_existing_subdir = tmp_path / "old_data"
        pre_existing_subdir.mkdir()

        result = initializer.create_project(
            tmp_path, project_name="Mixed", init_git=False, in_place=True
        )
        assert result == tmp_path
        # Pre-existing files preserved
        assert pre_existing.read_text(encoding="utf-8") == "my notes"
        assert pre_existing_subdir.is_dir()
        # anappt structure created
        assert (tmp_path / "data").is_dir()
        assert (tmp_path / ".anappt" / "state.yaml").is_file()
        assert (tmp_path / ".anappt" / "memory.md").is_file()
        assert (tmp_path / "report.yaml").exists()

    def test_in_place_skips_existing_files(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        """In-place init does not overwrite pre-existing template targets."""
        # Pre-existing report.yaml with custom content.
        custom_report = tmp_path / "report.yaml"
        custom_report.write_text("custom: value\n", encoding="utf-8")

        initializer.create_project(
            tmp_path, project_name="ShouldNotOverwrite", init_git=False, in_place=True
        )

        # The custom content must be preserved.
        assert custom_report.read_text(encoding="utf-8") == "custom: value\n"

    def test_in_place_does_not_clobber_state_yaml(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        """In-place init preserves an existing state.yaml (re-init is a no-op)."""
        anappt_dir = tmp_path / ".anappt"
        anappt_dir.mkdir(parents=True)
        state_file = anappt_dir / "state.yaml"
        state_file.write_text("preserved: true\n", encoding="utf-8")

        initializer.create_project(
            tmp_path, project_name="Ignored", init_git=False, in_place=True
        )

        assert state_file.read_text(encoding="utf-8") == "preserved: true\n"

    def test_in_place_creates_missing_anappt_subdir(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        """In-place init creates .anappt/session_history even when .anappt exists."""
        (tmp_path / ".anappt").mkdir(parents=True)

        initializer.create_project(
            tmp_path, project_name="HasAnappt", init_git=False, in_place=True
        )

        assert (tmp_path / ".anappt" / "session_history").is_dir()
        assert (tmp_path / ".anappt" / "state.yaml").is_file()
        assert (tmp_path / ".anappt" / "memory.md").is_file()

    def test_convenience_function_in_place(self, tmp_path: Path) -> None:
        """The create_project convenience function passes through in_place."""
        result = create_project(
            tmp_path, project_name="Conv", init_git=False, in_place=True
        )
        assert result == tmp_path
        assert (tmp_path / ".anappt" / "state.yaml").is_file()


class TestIsAnapptProject:
    """Tests for is_anappt_project function (Task A2)."""

    def test_valid_project(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "valid_project"
        initializer.create_project(project_dir, init_git=False)

        assert is_anappt_project(project_dir) is True

    def test_state_yaml_only_no_report_yaml(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        """A project with state.yaml but no report.yaml is valid (S1 not done)."""
        project_dir = tmp_path / "s1_pending"
        initializer.create_project(project_dir, init_git=False)
        (project_dir / "report.yaml").unlink()

        assert is_anappt_project(project_dir) is True

    def test_missing_anappt_dir(self, tmp_path: Path) -> None:
        """No .anappt directory at all -> not a project."""
        project_dir = tmp_path / "invalid"
        project_dir.mkdir()
        (project_dir / "report.yaml").write_text("project:\n  name: test", encoding="utf-8")

        assert is_anappt_project(project_dir) is False

    def test_anappt_dir_but_no_state_yaml(self, tmp_path: Path) -> None:
        """.anappt/ exists but no state.yaml -> not a project."""
        project_dir = tmp_path / "invalid2"
        (project_dir / ".anappt").mkdir(parents=True)

        assert is_anappt_project(project_dir) is False

    def test_report_yaml_but_no_state_yaml(self, tmp_path: Path) -> None:
        """report.yaml present but no state.yaml -> not a project.

        This guards against treating a hand-created report.yaml as a project
        when init has not actually been run.
        """
        project_dir = tmp_path / "only_report"
        project_dir.mkdir()
        (project_dir / ".anappt").mkdir(parents=True)
        (project_dir / "report.yaml").write_text("project:\n  name: test", encoding="utf-8")

        assert is_anappt_project(project_dir) is False

    def test_empty_directory(self, tmp_path: Path) -> None:
        assert is_anappt_project(tmp_path) is False

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        assert is_anappt_project(tmp_path / "nonexistent") is False
