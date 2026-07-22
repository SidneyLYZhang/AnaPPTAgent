"""Session logger for AnaPPTAgent.

Logs agent and user messages to Markdown files in the session_history
directory, providing a persistent conversation record per stage.

File naming (Task D1): ``YYYY-MM-DD_<stage>.md`` using the UTC date.
Same-day same-stage flushes are *appended* (separated by ``---``) rather
than overwritten, so a single file collects every session block for a
given (day, stage) pair. Each block carries an LLM-generated core
summary at the top (``## 核心摘要``) followed by the timestamped dialog
record (``### 对话记录``).

Module-level :func:`read_history` (Task D3) lets the LLM read past
session documents by stage ID, date, or in full.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from anappt.i18n import t
from anappt.llm.models import ModelRole
from anappt.llm.provider import AnaPPTLLM

# System prompt for the per-session core-summary LLM call. Hard-coded
# Chinese per the spec ("LLM 系统提示文案可硬编码中文常量").
_SUMMARY_SYSTEM_PROMPT = "根据以下对话生成核心摘要,说明本次对话重点,1-3 句。"


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
        # LLM-generated core summary for the current buffered session.
        # Populated by finalize_summary(); consumed and reset by flush().
        self._pending_summary: str | None = None

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

    def finalize_summary(self, llm: AnaPPTLLM, role: ModelRole) -> str:
        """Generate an LLM core summary for the current buffered session.

        Asks the LLM to produce a 1–3 sentence Chinese summary of the
        buffered entries. The summary is cached on ``self._pending_summary``
        so the next :meth:`flush` will embed it at the top of the written
        block (under ``## 核心摘要``). When no entries are buffered the
        pending summary is cleared and an empty string is returned.

        Args:
            llm: LLM provider used to generate the summary.
            role: Model role to invoke.

        Returns:
            The generated summary text (stripped). May be empty when
            the buffer is empty or the LLM returns nothing.
        """
        if not self.entries:
            self._pending_summary = ""
            return ""

        full_text = self.get_full_text()
        if not full_text.strip():
            self._pending_summary = ""
            return ""

        messages = [
            {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": full_text},
        ]
        summary = (llm.chat(role, messages) or "").strip()
        self._pending_summary = summary
        return summary

    def flush(self) -> Path | None:
        """Write buffered entries to the session log file.

        File naming follows ``YYYY-MM-DD_<stage>.md`` (UTC date). When
        the file already exists (same day + same stage), the new block
        is *appended* after a ``---`` separator rather than overwriting.
        Each block is structured as::

            ## 核心摘要
            <summary or 未生成摘要>

            ### 对话记录

            ## Agent

            [<timestamp>]

            <content>

            ## 用户

            [<timestamp>]

            <content>

        System entries are skipped in the rendered dialog record because
        the core summary already describes the session.

        Returns:
            Path to the written file, or None if no entries to flush
            or no stage is set.
        """
        if not self.entries:
            return None
        if not self.current_stage:
            return None

        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        filename = f"{date_str}_{self.current_stage}.md"
        filepath = self.session_dir / filename

        summary_text = (
            self._pending_summary
            if self._pending_summary
            else t("session.summary_not_generated")
        )

        block_lines: list[str] = []
        # Core summary section
        block_lines.append(t("session.summary_section"))
        block_lines.append(summary_text)
        block_lines.append("")
        # Dialog record section
        block_lines.append(t("session.dialog_section"))
        block_lines.append("")
        for role, timestamp, content in self.entries:
            if role == "system":
                # Internal session marker — skip in rendered dialog;
                # the core summary at the top covers this role.
                continue
            if role == "agent":
                header = t("session.agent_header")
            elif role == "user":
                header = t("session.user_header")
            else:
                header = f"## {role}"
            block_lines.append(header)
            block_lines.append("")
            block_lines.append(f"[{timestamp}]")
            block_lines.append("")
            block_lines.append(content)
            block_lines.append("")

        new_block = "\n".join(block_lines).rstrip() + "\n"

        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8").rstrip()
            filepath.write_text(
                f"{existing}\n\n{t('session.separator')}\n\n{new_block}",
                encoding="utf-8",
            )
        else:
            filepath.write_text(new_block, encoding="utf-8")

        self.entries = []
        self._pending_summary = None
        return filepath

    def get_full_text(self) -> str:
        """Return buffered entries as plain ``角色: 内容`` lines.

        Used as input to :meth:`MemoryManager.update`. System entries
        are skipped; only agent/user entries are emitted, one per line,
        prefixed with the localized role label.

        Returns:
            Newline-joined ``角色: 内容`` lines.
        """
        lines: list[str] = []
        for role, _timestamp, content in self.entries:
            if role == "system":
                continue
            if role == "agent":
                role_label = t("session.agent_role")
            elif role == "user":
                role_label = t("session.user_role")
            else:
                role_label = role
            lines.append(f"{role_label}: {content}")
        return "\n".join(lines)

    def get_session_file(self) -> Path:
        """Return the path to the current session file.

        Uses the same date-based naming as :meth:`flush`. The date is
        computed at call time, so the returned path may differ across
        UTC-day boundaries.

        Returns:
            Path to ``YYYY-MM-DD_<stage>.md`` if a stage is set,
            otherwise ``session.md``.
        """
        if not self.current_stage:
            return self.session_dir / "session.md"
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        return self.session_dir / f"{date_str}_{self.current_stage}.md"

    def get_entries(self) -> list[tuple[str, str, str]]:
        """Return the current buffered entries.

        Returns:
            List of (role, timestamp, content) tuples.
        """
        return list(self.entries)

    def clear(self) -> None:
        """Clear all buffered entries without flushing."""
        self.entries = []
        self._pending_summary = None


def read_history(session_dir: str | Path, target: str = "all") -> str:
    """Read past session-history documents by stage ID, date, or in full.

    Reads ``YYYY-MM-DD_<stage>.md`` files from ``session_dir`` matching
    the ``target`` selector, sorted by filename, and returns their
    concatenated contents separated by a ``---`` rule.

    Matching rules:

    - ``target == "all"`` (default): include every ``*.md`` file in the
      directory. Legacy ``<stage>_session.md`` files are also included.
    - ``target`` looks like a date (``YYYY-MM-DD`` prefix): include
      files whose name starts with ``target``.
    - ``target`` is treated as a stage ID otherwise: include files of
      the form ``<date>_<stage>.md`` whose ``<stage>`` segment equals
      ``target``, *and* legacy files named ``<stage>_session.md``.

    Args:
        session_dir: Directory holding session-history ``*.md`` files.
        target: ``"all"``, a date string (``YYYY-MM-DD``), or a stage
            ID (e.g. ``"S4"``).

    Returns:
        Concatenated file contents (with ``---`` separators), or an
        empty string when no files match or the directory is absent.
    """
    directory = Path(session_dir)
    if not directory.is_dir():
        return ""

    target = (target or "all").strip()
    if not target:
        target = "all"

    # Heuristic: treat as a date when it begins with a 4-digit year
    # followed by ``-``. Otherwise treat as a stage ID.
    is_date_target = (
        len(target) >= 5
        and target[:4].isdigit()
        and target[4] == "-"
    )

    matched_files: list[Path] = []
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        if not entry.name.endswith(".md"):
            continue

        name = entry.name

        if target == "all":
            matched_files.append(entry)
            continue

        if is_date_target:
            # Date target: filename must start with the date string.
            if name.startswith(target):
                matched_files.append(entry)
            continue

        # Stage-ID target: match new ``YYYY-MM-DD_<stage>.md`` naming
        # (the segment after the first ``_`` must equal the target) and
        # legacy ``<stage>_session.md`` naming.
        if name == f"{target}_session.md":
            matched_files.append(entry)
            continue
        # New naming: YYYY-MM-DD_<stage>.md — split on first ``_`` only
        # so stages containing underscores would still match. Stages
        # in this project are S1..S6 so a simple split is sufficient.
        # Strip the trailing ``.md`` before comparing the stage segment.
        stem = name[: -len(".md")] if name.endswith(".md") else name
        if "_" in stem:
            _date_part, _, stage_part = stem.partition("_")
            if stage_part == target:
                matched_files.append(entry)

    if not matched_files:
        return ""

    matched_files.sort(key=lambda p: p.name)

    separator = f"\n\n{t('session.separator')}\n\n"
    parts: list[str] = []
    for f in matched_files:
        try:
            parts.append(f.read_text(encoding="utf-8").rstrip())
        except OSError:
            # Skip unreadable files rather than failing the whole read.
            continue
    return separator.join(parts) + "\n"
