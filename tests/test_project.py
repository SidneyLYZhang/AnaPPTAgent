"""Tests for project initialization."""

from __future__ import annotations

from pathlib import Path

import pytest

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


class TestIsAnapptProject:
    """Tests for is_anappt_project function."""

    def test_valid_project(
        self, initializer: ProjectInitializer, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "valid_project"
        initializer.create_project(project_dir, init_git=False)

        assert is_anappt_project(project_dir) is True

    def test_missing_anappt_dir(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "invalid"
        project_dir.mkdir()
        (project_dir / "report.yaml").write_text("project:\n  name: test", encoding="utf-8")

        assert is_anappt_project(project_dir) is False

    def test_missing_report_yaml(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "invalid2"
        (project_dir / ".anappt").mkdir(parents=True)

        assert is_anappt_project(project_dir) is False

    def test_empty_directory(self, tmp_path: Path) -> None:
        assert is_anappt_project(tmp_path) is False

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        assert is_anappt_project(tmp_path / "nonexistent") is False
