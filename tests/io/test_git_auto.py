"""Tests for the Git auto-commit module."""

import subprocess

import pytest

from anappt.i18n import set_locale
from anappt.io.git_auto import GitAutoCommit


@pytest.fixture
def git_project(tmp_path):
    """Create a temporary project with git initialized."""
    project = tmp_path / "git_project"
    project.mkdir()
    # Initialize git
    subprocess.run(["git", "init"], cwd=str(project), capture_output=True, timeout=10)
    # Set a default user for commits
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(project),
        capture_output=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(project),
        capture_output=True,
        timeout=10,
    )
    return project


@pytest.fixture
def non_git_project(tmp_path):
    """Create a temporary project without git."""
    project = tmp_path / "non_git_project"
    project.mkdir()
    return project


class TestIsGitRepo:
    """Test git repository detection."""

    def test_git_repo_detected(self, git_project):
        gac = GitAutoCommit(git_project)
        assert gac.is_git_repo() is True

    def test_non_git_repo_detected(self, non_git_project):
        gac = GitAutoCommit(non_git_project)
        assert gac.is_git_repo() is False

    def test_nonexistent_dir(self, tmp_path):
        gac = GitAutoCommit(tmp_path / "nonexistent")
        assert gac.is_git_repo() is False


class TestCommitOnStageComplete:
    """Test stage completion commits."""

    def test_commit_message_format(self, git_project):
        set_locale("en")
        # Create a file to commit
        (git_project / "output.txt").write_text("test content")

        gac = GitAutoCommit(git_project)
        result = gac.commit_on_stage_complete("S1", "Topic Definition", ["output.txt"])
        assert result is True

        # Check the commit message
        log = subprocess.run(
            ["git", "log", "--format=%s", "-1"],
            cwd=str(git_project),
            capture_output=True,
            text=True,
        )
        assert "feat(S1)" in log.stdout
        assert "complete" in log.stdout
        assert "Topic Definition" in log.stdout
        assert "output.txt" in log.stdout

    def test_non_git_silent_skip(self, non_git_project):
        gac = GitAutoCommit(non_git_project)
        result = gac.commit_on_stage_complete("S1", "Topic", ["file.txt"])
        assert result is True  # Should not raise, returns True


class TestCommitOnConfirm:
    """Test confirmation commits."""

    def test_commit_message_format(self, git_project):
        set_locale("en")
        (git_project / "report.yaml").write_text("test: true")

        gac = GitAutoCommit(git_project)
        gac.commit_on_stage_complete("S1", "Topic", ["report.yaml"])

        # Make a change so the confirm commit has something to commit
        (git_project / "report.yaml").write_text("test: true\nconfirmed: true")

        result = gac.commit_on_confirm("S1", "Topic Definition")
        assert result is True

        log = subprocess.run(
            ["git", "log", "--format=%s", "-1"],
            cwd=str(git_project),
            capture_output=True,
            text=True,
        )
        assert "feat(S1)" in log.stdout
        assert "confirm" in log.stdout
        assert "Topic Definition" in log.stdout

    def test_non_git_silent_skip(self, non_git_project):
        gac = GitAutoCommit(non_git_project)
        result = gac.commit_on_confirm("S1", "Topic")
        assert result is True


class TestCommitOnExit:
    """Test exit commits."""

    def test_commit_message_format(self, git_project):
        set_locale("en")
        (git_project / "state.yaml").write_text("test: true")

        gac = GitAutoCommit(git_project)
        result = gac.commit_on_exit()
        assert result is True

        log = subprocess.run(
            ["git", "log", "--format=%s", "-1"],
            cwd=str(git_project),
            capture_output=True,
            text=True,
        )
        assert "chore: auto-save on exit" in log.stdout

    def test_non_git_silent_skip(self, non_git_project):
        gac = GitAutoCommit(non_git_project)
        result = gac.commit_on_exit()
        assert result is True


class TestSessionHistoryExclusion:
    """Test that session_history is excluded from commits."""

    def test_session_history_not_committed(self, git_project):
        set_locale("en")
        # Create session_history with content
        session_dir = git_project / ".anappt" / "session_history"
        session_dir.mkdir(parents=True)
        (session_dir / "2026-07-17.md").write_text("# Session log")

        # Create a real file to commit
        (git_project / "output.txt").write_text("real output")

        gac = GitAutoCommit(git_project)
        gac.commit_on_exit()

        # Check that session_history was NOT committed
        show = subprocess.run(
            ["git", "show", "--stat", "HEAD"],
            cwd=str(git_project),
            capture_output=True,
            text=True,
        )
        # The output.txt should be in the commit, but session_history should not
        assert "output.txt" in show.stdout
        assert "session_history" not in show.stdout
