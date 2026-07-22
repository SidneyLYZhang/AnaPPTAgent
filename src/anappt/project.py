"""Project initialization for AnaPPTAgent.

Creates a new project directory with the standard structure,
copies template files, and optionally initializes a git repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from anappt.i18n import t
from anappt.io.state import StateManager

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
        in_place: bool = False,
    ) -> Path:
        """Create a new project with the standard structure.

        Args:
            project_dir: Path where the project will be created.
            project_name: Name of the project (used in report.yaml/state.yaml).
            init_git: Whether to initialize a git repository.
            in_place: When True, initialize ``project_dir`` in place even if it
                is non-empty (existing files/directories are skipped, only
                missing ones are created). When False (default), raise
                ``FileExistsError`` if the directory exists and is non-empty.

        Returns:
            Path to the created project directory.

        Raises:
            FileExistsError: If ``in_place`` is False and the directory already
                exists and is not empty.
        """
        project_path = Path(project_dir)

        # Check if directory exists and is not empty (only enforced for
        # subdirectory mode; in-place mode tolerates pre-existing content).
        if not in_place:
            if project_path.exists() and any(project_path.iterdir()):
                raise FileExistsError(t("project.dir_exists", path=str(project_path)))

        # Create directory structure
        project_path.mkdir(parents=True, exist_ok=True)
        for dir_name in _PROJECT_DIRS:
            (project_path / dir_name).mkdir(parents=True, exist_ok=True)

        # Copy template files (skip existing when in_place to avoid clobbering)
        self._copy_templates(project_path, project_name, skip_existing=in_place)

        # Write init markers: .anappt/state.yaml + .anappt/memory.md
        self._write_init_markers(project_path, project_name)

        # Initialize git if requested
        if init_git:
            self._init_git(project_path)

        return project_path

    def _copy_templates(
        self,
        project_path: Path,
        project_name: str,
        skip_existing: bool = False,
    ) -> None:
        """Copy template files to the project directory.

        Args:
            project_path: Target project directory.
            project_name: Project name to substitute in templates.
            skip_existing: When True, do not overwrite files that already exist
                at the target path (used for in-place initialization).
        """
        for tmpl_rel in _TEMPLATE_FILES:
            tmpl_src = self.templates_dir / tmpl_rel
            if not tmpl_src.exists():
                continue

            # Determine target path (strip .tmpl suffix)
            target_rel = tmpl_rel.removesuffix(".tmpl")
            target_path = project_path / target_rel

            if skip_existing and target_path.exists():
                continue

            # Read, substitute, and write
            content = tmpl_src.read_text(encoding="utf-8")
            if project_name:
                content = content.replace('name: ""', f'name: "{project_name}"')
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")

    def _write_init_markers(
        self, project_path: Path, project_name: str
    ) -> None:
        """Write the init marker files: ``.anappt/state.yaml`` and ``.anappt/memory.md``.

        ``state.yaml`` is the authoritative init marker checked by
        :func:`is_anappt_project`. ``memory.md`` is the seed project memory
        file (empty until the conversation pipeline updates it). Both files are
        only written if they do not already exist, so re-running init on an
        existing project is a no-op for these markers.

        Args:
            project_path: Target project directory.
            project_name: Project name recorded in ``state.yaml``.
        """
        anappt_dir = project_path / ".anappt"
        anappt_dir.mkdir(parents=True, exist_ok=True)

        state_file = anappt_dir / "state.yaml"
        if not state_file.exists():
            # StateManager loads create_initial_state() when the file is
            # absent; we then stamp the project_name and persist.
            sm = StateManager(state_file)
            sm.state.project_name = project_name
            sm.save()

        memory_file = anappt_dir / "memory.md"
        if not memory_file.exists():
            memory_file.write_text("", encoding="utf-8")

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
    in_place: bool = False,
) -> Path:
    """Create a new AnaPPTAgent project.

    Convenience function wrapping ProjectInitializer.

    Args:
        project_dir: Path where the project will be created.
        project_name: Name of the project.
        init_git: Whether to initialize a git repository.
        in_place: When True, initialize ``project_dir`` in place even if it is
            non-empty (existing files are skipped). When False (default), raise
            ``FileExistsError`` if the directory is non-empty.

    Returns:
        Path to the created project directory.
    """
    initializer = ProjectInitializer()
    return initializer.create_project(
        project_dir, project_name, init_git, in_place=in_place
    )


def is_anappt_project(directory: str | Path) -> bool:
    """Check if a directory is an AnaPPTAgent project.

    A valid project is identified solely by the presence of the init marker
    file ``.anappt/state.yaml``. ``report.yaml`` is NOT required because S1
    is responsible for generating it via conversation.

    Args:
        directory: Directory to check.

    Returns:
        True if the directory is an AnaPPTAgent project.
    """
    directory = Path(directory)
    state_file = directory / ".anappt" / "state.yaml"
    return state_file.is_file()
