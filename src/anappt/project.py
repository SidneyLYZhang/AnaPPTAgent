"""Project initialization for AnaPPTAgent.

Creates a new project directory with the standard structure,
copies template files, and optionally initializes a git repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from anappt.i18n import t

# Standard project directory structure
_PROJECT_DIRS: list[str] = [
    "data",
    "output",
    "output/images",
    ".anappt",
    ".anappt/session_history",
]

# Template files to copy (relative to templates/project/)
_TEMPLATE_FILES: list[str] = [
    "report.yaml.tmpl",
    ".gitignore.tmpl",
    "data/README.md.tmpl",
]


class ProjectInitializer:
    """Handles creation of new AnaPPTAgent projects.

    Creates the standard directory structure, copies template files,
    and optionally initializes a git repository.
    """

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        """Initialize the project creator.

        Args:
            templates_dir: Path to the templates directory.
                           Defaults to the package's templates directory.
        """
        if templates_dir is None:
            self.templates_dir: Path = Path(__file__).parent.parent.parent / "templates" / "project"
        else:
            self.templates_dir = Path(templates_dir)

    def create_project(
        self,
        project_dir: str | Path,
        project_name: str = "",
        init_git: bool = True,
    ) -> Path:
        """Create a new project with the standard structure.

        Args:
            project_dir: Path where the project will be created.
            project_name: Name of the project (used in report.yaml).
            init_git: Whether to initialize a git repository.

        Returns:
            Path to the created project directory.

        Raises:
            FileExistsError: If the directory already exists and is not empty.
        """
        project_path = Path(project_dir)

        # Check if directory exists and is not empty
        if project_path.exists() and any(project_path.iterdir()):
            raise FileExistsError(t("project.dir_exists", path=str(project_path)))

        # Create directory structure
        project_path.mkdir(parents=True, exist_ok=True)
        for dir_name in _PROJECT_DIRS:
            (project_path / dir_name).mkdir(parents=True, exist_ok=True)

        # Copy template files
        self._copy_templates(project_path, project_name)

        # Initialize git if requested
        if init_git:
            self._init_git(project_path)

        return project_path

    def _copy_templates(self, project_path: Path, project_name: str) -> None:
        """Copy template files to the project directory.

        Args:
            project_path: Target project directory.
            project_name: Project name to substitute in templates.
        """
        for tmpl_rel in _TEMPLATE_FILES:
            tmpl_src = self.templates_dir / tmpl_rel
            if not tmpl_src.exists():
                continue

            # Determine target path (strip .tmpl suffix)
            target_rel = tmpl_rel.removesuffix(".tmpl")
            target_path = project_path / target_rel

            # Read, substitute, and write
            content = tmpl_src.read_text(encoding="utf-8")
            if project_name:
                content = content.replace('name: ""', f'name: "{project_name}"')
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")

    def _init_git(self, project_path: Path) -> None:
        """Initialize a git repository in the project directory.

        Args:
            project_path: Path to the project directory.
        """
        try:
            subprocess.run(
                ["git", "init"],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            # Initial commit
            subprocess.run(
                ["git", "add", "."],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            subprocess.run(
                ["git", "commit", "-m", "chore: initialize project"],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            # Git not available or failed — not critical
            pass


def create_project(
    project_dir: str | Path,
    project_name: str = "",
    init_git: bool = True,
) -> Path:
    """Create a new AnaPPTAgent project.

    Convenience function wrapping ProjectInitializer.

    Args:
        project_dir: Path where the project will be created.
        project_name: Name of the project.
        init_git: Whether to initialize a git repository.

    Returns:
        Path to the created project directory.
    """
    initializer = ProjectInitializer()
    return initializer.create_project(project_dir, project_name, init_git)


def is_anappt_project(directory: str | Path) -> bool:
    """Check if a directory is an AnaPPTAgent project.

    A valid project has a .anappt directory and a report.yaml file.

    Args:
        directory: Directory to check.

    Returns:
        True if the directory is an AnaPPTAgent project.
    """
    directory = Path(directory)
    anappt_dir = directory / ".anappt"
    report_yaml = directory / "report.yaml"
    return anappt_dir.is_dir() and report_yaml.is_file()
