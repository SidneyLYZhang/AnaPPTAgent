"""Automatic Git commit utility for AnaPPTAgent.

Automatically commits changes at three key points:
1. On stage completion (content generation)
2. On user confirmation
3. On process exit

Follows Conventional Commits specification. Silently skips if not a git repo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from anappt.i18n import t


class GitAutoCommit:
    """Manages automatic git commits for a project directory.

    Handles three commit trigger points:
    - Stage completion: feat(S{n}): complete {stage_name} - {files}
    - User confirmation: feat(S{n}): confirm {stage_name}
    - Process exit: chore: auto-save on exit

    If the project directory is not a git repository, all operations
    silently skip without raising errors.
    """

    def __init__(self, project_dir: str | Path) -> None:
        """Initialize the Git auto-commit manager.

        Args:
            project_dir: Root directory of the analysis project.
        """
        self.project_dir = Path(project_dir)

    def is_git_repo(self) -> bool:
        """Check if the project directory is inside a git repository.

        Returns:
            True if this is a git repository.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            return result.returncode == 0 and result.stdout.strip() == "true"
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return False

    def _git_add(self, paths: list[str] | None = None) -> None:
        """Stage files for commit, excluding session_history.

        Args:
            paths: Specific paths to add. If None, adds all except session_history.
        """
        if paths:
            for p in paths:
                subprocess.run(
                    ["git", "add", p],
                    cwd=str(self.project_dir),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
        else:
            # Add all files except .anappt/session_history/
            subprocess.run(
                ["git", "add", "."],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            # Reset session_history if it was staged
            session_history = self.project_dir / ".anappt" / "session_history"
            if session_history.exists():
                subprocess.run(
                    ["git", "reset", "--", str(session_history.relative_to(self.project_dir))],
                    cwd=str(self.project_dir),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )

    def _git_commit(self, message: str) -> bool:
        """Create a git commit with the given message.

        Args:
            message: Commit message following Conventional Commits.

        Returns:
            True if commit was created (or nothing to commit), False on error.
        """
        try:
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            # Return code 0 means success, code 1 means "nothing to commit" which is fine
            return result.returncode in (0, 1)
        except (subprocess.SubprocessError, OSError):
            return False

    def commit_on_stage_complete(
        self, stage_id: str, stage_name: str, files: list[str] | None = None
    ) -> bool:
        """Commit after a stage's content has been written to disk.

        Args:
            stage_id: Stage identifier (e.g., 'S1').
            stage_name: Human-readable stage name.
            files: List of produced file paths to stage.

        Returns:
            True if commit succeeded or not a git repo (silent skip).
        """
        if not self.is_git_repo():
            return True

        self._git_add(files)
        files_str = ", ".join(files) if files else "output"
        message = t(
            "git.commit_stage_complete",
            stage_id=stage_id,
            stage_name=stage_name,
            files=files_str,
        )
        return self._git_commit(message)

    def commit_on_confirm(self, stage_id: str, stage_name: str) -> bool:
        """Commit after user confirms a stage's output.

        Args:
            stage_id: Stage identifier.
            stage_name: Human-readable stage name.

        Returns:
            True if commit succeeded or not a git repo.
        """
        if not self.is_git_repo():
            return True

        self._git_add()
        message = t("git.commit_confirm", stage_id=stage_id, stage_name=stage_name)
        return self._git_commit(message)

    def commit_on_exit(self) -> bool:
        """Commit any unsaved changes when the process exits.

        Returns:
            True if commit succeeded or not a git repo.
        """
        if not self.is_git_repo():
            return True

        self._git_add()
        message = t("git.commit_on_exit")
        return self._git_commit(message)
