"""Core type definitions for the AnaPPTAgent pipeline.

Defines PipelineContext, StageOutput, and the InteractiveUIProtocol
that stages and the orchestrator depend on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from anappt.io.config import ReportConfig
from anappt.io.git_auto import GitAutoCommit
from anappt.io.session import SessionLogger
from anappt.io.state import StateManager
from anappt.llm.models import ModelRole
from anappt.llm.provider import AnaPPTLLM


@runtime_checkable
class InteractiveUIProtocol(Protocol):
    """Protocol defining the UI interface that stages and orchestrator use.

    The actual implementation is provided by InteractiveUI in cli.py.
    Using a Protocol allows stages to depend on the interface without
    importing the concrete class (avoids circular imports).
    """

    def print(self, message: str) -> None:
        """Print a message to the user.

        Args:
            message: Text to display.
        """
        ...

    def input(self, prompt: str) -> str:
        """Read a line of input from the user.

        Args:
            prompt: Prompt text to display.

        Returns:
            The user's input string.
        """
        ...

    def confirm(self, prompt: str) -> bool:
        """Ask the user for a yes/no confirmation.

        Args:
            prompt: Confirmation prompt text.

        Returns:
            True if the user confirmed.
        """
        ...

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        """Display a table to the user.

        Args:
            headers: Column header strings.
            rows: List of row data, each row a list of cell strings.
        """
        ...

    def progress(self, message: str) -> None:
        """Show a progress/status message.

        Args:
            message: Progress message to display.
        """
        ...


class PipelineContext:
    """Shared context passed to every stage during pipeline execution.

    Holds references to all services a stage might need: configuration,
    LLM provider, state manager, UI, session logger, and git auto-commit.

    Attributes:
        project_dir: Root directory of the analysis project.
        config: Parsed report.yaml configuration.
        llm: LLM provider instance.
        state: Pipeline state manager.
        ui: Interactive UI protocol implementation (may be None in tests).
        session: Session logger for conversation history.
        git: Git auto-commit manager.
        output_dir: Directory for stage output artifacts.
    """

    def __init__(
        self,
        project_dir: str | Path,
        config: ReportConfig,
        llm: AnaPPTLLM,
        state: StateManager,
        ui: InteractiveUIProtocol | None = None,
        session: SessionLogger | None = None,
        git: GitAutoCommit | None = None,
        output_dir: str | Path | None = None,
    ) -> None:
        """Initialize the pipeline context.

        Args:
            project_dir: Root directory of the analysis project.
            config: Parsed report configuration.
            llm: LLM provider instance.
            state: Pipeline state manager.
            ui: Interactive UI (optional, None for headless/tests).
            session: Session logger (optional).
            git: Git auto-commit manager (optional).
            output_dir: Output directory (defaults to project_dir/output).
        """
        self.project_dir: Path = Path(project_dir)
        self.config: ReportConfig = config
        self.llm: AnaPPTLLM = llm
        self.state: StateManager = state
        self.ui: InteractiveUIProtocol | None = ui
        self.session: SessionLogger | None = session
        self.git: GitAutoCommit | None = git
        self.output_dir: Path = Path(output_dir) if output_dir else self.project_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_artifact_path(self, filename: str) -> Path:
        """Get the full path for an output artifact file.

        Args:
            filename: Name of the artifact file.

        Returns:
            Full path under the output directory.
        """
        return self.output_dir / filename

    def get_anappt_path(self, filename: str) -> Path:
        """Get a path under the .anappt directory.

        Args:
            filename: Name of the file.

        Returns:
            Full path under project_dir/.anappt/.
        """
        path = self.project_dir / ".anappt" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def get_data_dir(self) -> Path:
        """Get the data directory path.

        Returns:
            Path to project_dir/data.
        """
        return self.project_dir / "data"


class StageOutput:
    """Result of running a single pipeline stage.

    Attributes:
        success: Whether the stage completed successfully.
        artifacts: List of artifact file paths produced by the stage.
        summary: Human-readable summary of the stage output.
        data: Optional structured data produced by the stage.
        next_action: Suggested next action (e.g., 'confirm' or 'revise').
    """

    def __init__(
        self,
        success: bool = True,
        artifacts: list[str] | None = None,
        summary: str = "",
        data: dict[str, Any] | None = None,
        next_action: str = "confirm",
    ) -> None:
        """Initialize the stage output.

        Args:
            success: Whether the stage succeeded.
            artifacts: List of artifact paths (relative or absolute).
            summary: Human-readable summary.
            data: Optional structured data payload.
            next_action: Suggested next action.
        """
        self.success: bool = success
        self.artifacts: list[str] = artifacts or []
        self.summary: str = summary
        self.data: dict[str, Any] = data or {}
        self.next_action: str = next_action

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary.

        Returns:
            Dictionary representation of the stage output.
        """
        return {
            "success": self.success,
            "artifacts": list(self.artifacts),
            "summary": self.summary,
            "data": dict(self.data),
            "next_action": self.next_action,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageOutput:
        """Create from a dictionary.

        Args:
            data: Dictionary with stage output fields.

        Returns:
            StageOutput instance.
        """
        return cls(
            success=data.get("success", True),
            artifacts=data.get("artifacts", []),
            summary=data.get("summary", ""),
            data=data.get("data", {}),
            next_action=data.get("next_action", "confirm"),
        )


def model_role_for_stage(stage_id: str) -> ModelRole:
    """Return the model role appropriate for a given stage.

    S1-S2 use 'reasoning', S4 uses 'analysis', S5-S6 use 'writing'.
    S3 is data loading (no LLM needed) but returns 'reasoning' as default.

    Args:
        stage_id: Stage identifier (e.g., 'S1').

    Returns:
        Model role string: 'reasoning', 'analysis', or 'writing'.
    """
    role_map: dict[str, ModelRole] = {
        "S1": "reasoning",
        "S2": "reasoning",
        "S3": "reasoning",
        "S4": "analysis",
        "S5": "writing",
        "S6": "writing",
    }
    return role_map.get(stage_id, "reasoning")
