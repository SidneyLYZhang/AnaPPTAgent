"""Session logger for AnaPPTAgent.

Logs agent and user messages to Markdown files in the session_history
directory, providing a persistent conversation record per stage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from anappt.i18n import t


class SessionLogger:
    """Logs conversation messages to session history files.

    Each stage gets its own session log file under .anappt/session_history/.
    Messages are buffered in memory and flushed to disk on demand.

    Attributes:
        session_dir: Directory for session history files.
        current_stage: Current stage ID being logged.
        entries: Buffered log entries.
    """

    def __init__(self, session_dir: str | Path) -> None:
        """Initialize the session logger.

        Args:
            session_dir: Path to the session history directory
                         (typically project_dir/.anappt/session_history).
        """
        self.session_dir: Path = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.current_stage: str = ""
        self.entries: list[tuple[str, str, str]] = []  # (role, timestamp, content)

    def new_session(self, stage_id: str) -> None:
        """Start a new session for a stage.

        Flushes any pending entries and resets the buffer for the new stage.

        Args:
            stage_id: Stage identifier (e.g., 'S1').
        """
        self.flush()
        self.current_stage = stage_id
        self.entries = []
        timestamp = datetime.now(UTC).isoformat()
        self.entries.append(("system", timestamp, t("session.new_session", stage_id=stage_id)))

    def log_agent(self, content: str) -> None:
        """Log an agent message.

        Args:
            content: The agent's message content.
        """
        timestamp = datetime.now(UTC).isoformat()
        self.entries.append(("agent", timestamp, content))

    def log_user(self, content: str) -> None:
        """Log a user message.

        Args:
            content: The user's message content.
        """
        timestamp = datetime.now(UTC).isoformat()
        self.entries.append(("user", timestamp, content))

    def flush(self) -> Path | None:
        """Write buffered entries to the session log file.

        Returns:
            Path to the written file, or None if no entries to flush.
        """
        if not self.entries:
            return None
        if not self.current_stage:
            return None

        filename = f"{self.current_stage}_session.md"
        filepath = self.session_dir / filename

        lines: list[str] = []
        for role, timestamp, content in self.entries:
            if role == "system":
                lines.append(f"# {content}\n")
            elif role == "agent":
                lines.append(f"{t('session.agent_header')}\n\n{content}\n")
            elif role == "user":
                lines.append(f"{t('session.user_header')}\n\n{content}\n")

        filepath.write_text("\n".join(lines), encoding="utf-8")
        self.entries = []
        return filepath

    def get_session_file(self) -> Path:
        """Return the path to the current session file.

        Returns:
            Path to the session file for the current stage.
        """
        if not self.current_stage:
            return self.session_dir / "session.md"
        return self.session_dir / f"{self.current_stage}_session.md"

    def get_entries(self) -> list[tuple[str, str, str]]:
        """Return the current buffered entries.

        Returns:
            List of (role, timestamp, content) tuples.
        """
        return list(self.entries)

    def clear(self) -> None:
        """Clear all buffered entries without flushing."""
        self.entries = []
