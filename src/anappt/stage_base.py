"""Abstract base class for all pipeline stages.

Each stage implements the run() method to produce output artifacts.
Stages are executed sequentially by the Orchestrator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from anappt.i18n import t
from anappt.io.state import STAGE_PREREQUISITES, StageStatus, StateManager
from anappt.llm.models import ModelRole
from anappt.types import PipelineContext, StageOutput, model_role_for_stage


class StageBase(ABC):
    """Abstract base class for a pipeline stage.

    Subclasses must define:
        - stage_id: Stage identifier (e.g., 'S1')
        - stage_name: i18n key for display name
        - run(ctx): Execute the stage and return StageOutput

    Attributes:
        stage_id: The stage identifier.
        stage_name: i18n key for the stage's display name.
    """

    stage_id: str = ""
    stage_name: str = ""

    @property
    def model_role(self) -> ModelRole:
        """Return the model role for this stage.

        Returns:
            Model role string based on the stage_id.
        """
        return model_role_for_stage(self.stage_id)

    def display_name(self) -> str:
        """Return the localized display name for this stage.

        Returns:
            Translated stage name.
        """
        return t(self.stage_name)

    def validate_prerequisites(self, state: StateManager) -> bool:
        """Check if all prerequisite stages are completed.

        Args:
            state: The pipeline state manager.

        Returns:
            True if all prerequisites are completed.
        """
        prereqs = STAGE_PREREQUISITES.get(self.stage_id, [])
        for prereq_id in prereqs:
            stage = state.get_stage(prereq_id)
            if stage is None or stage.status != StageStatus.COMPLETED:
                return False
        return True

    @abstractmethod
    def run(self, ctx: PipelineContext) -> StageOutput:
        """Execute the stage.

        Args:
            ctx: Pipeline context with all services.

        Returns:
            StageOutput with results, artifacts, and next action.
        """
        ...

    def get_artifacts(self, ctx: PipelineContext) -> list[str]:
        """Return list of artifact paths this stage produces.

        Override in subclasses to provide actual paths.

        Args:
            ctx: Pipeline context.

        Returns:
            List of artifact file names. Empty by default.
        """
        return []

    def _log_ui(self, ctx: PipelineContext, message: str) -> None:
        """Print a message to the UI if available.

        Args:
            ctx: Pipeline context.
            message: Message to display.
        """
        if ctx.ui is not None:
            ctx.ui.print(message)

    def _log_session(self, ctx: PipelineContext, content: str) -> None:
        """Log agent content to the session logger if available.

        Args:
            ctx: Pipeline context.
            content: Content to log.
        """
        if ctx.session is not None:
            ctx.session.log_agent(content)
