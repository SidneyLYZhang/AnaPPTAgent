"""Abstract base class for all pipeline stages.

Each stage implements the run() method to produce output artifacts.
Stages are executed sequentially by the Orchestrator.

Stages also expose a declarative interface used by the conversation-driven
TUI (``ConversationRunner``):

    - ``goal``: i18n key describing the stage's goal (shown to LLM/user).
    - ``get_artifacts(ctx)``: declared artifact paths relative to project root.
    - ``system_prompt_fragment(ctx)``: stage-specific system prompt fragment.
    - ``tools(ctx)``: subset of tool names the LLM may use in this stage.
    - ``is_ready(ctx)``: gate check that all expected artifacts exist.

The legacy ``run()`` method is preserved for backward compatibility with
the Orchestrator-based execution path; it will be removed once the
conversation runner is fully wired (Task C2-C4).
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

    Declarative attributes (used by the conversation-driven TUI):

        - goal: i18n key describing the stage's goal. Defaults to empty
          string (subclass should override to a meaningful key such as
          ``"s1.goal"``). Used to tell the LLM/user what this stage is
          about.

    Attributes:
        stage_id: The stage identifier.
        stage_name: i18n key for the stage's display name.
        goal: i18n key for the stage's goal description.
    """

    stage_id: str = ""
    stage_name: str = ""
    goal: str = ""

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

        Paths are relative to ``ctx.project_dir``. Override in subclasses
        to provide actual paths. Empty by default.

        Args:
            ctx: Pipeline context.

        Returns:
            List of artifact file names. Empty by default.
        """
        return []

    def system_prompt_fragment(self, ctx: PipelineContext) -> str:
        """Return the stage-specific system prompt fragment.

        Subclasses override this to inject stage guidance into the
        conversation runner's system prompt. The fragment is appended
        to the generic conversation system prompt. Returns an empty
        string by default.

        Args:
            ctx: Pipeline context.

        Returns:
            Stage-specific system prompt fragment (empty by default).
        """
        return ""

    def tools(self, ctx: PipelineContext) -> list[str]:
        """Return the subset of tool names the LLM may use in this stage.

        Tool names are strings from the canonical set:
        ``read_file``/``write_artifact``/``read_memory``/``read_history``/
        ``execute_python``/``search_web``/``fetch_url``/``render_deck``/
        ``export_pptx``/``list_stage_artifacts``.

        Returns an empty list by default; subclasses override to declare
        their usable tools.

        Args:
            ctx: Pipeline context.

        Returns:
            List of tool name strings enabled for this stage. Empty by
            default.
        """
        return []

    def is_ready(self, ctx: PipelineContext) -> bool:
        """Check whether this stage's expected artifacts are ready.

        The default implementation returns ``True`` if every path in
        :meth:`get_artifacts` exists relative to ``ctx.project_dir``.
        Subclasses override to add stronger validation (e.g. parsing
        YAML and checking required fields).

        Args:
            ctx: Pipeline context.

        Returns:
            True if all declared artifacts exist (or the stage declares
            no artifacts). Subclasses may strengthen this.
        """
        for rel_path in self.get_artifacts(ctx):
            if not (ctx.project_dir / rel_path).exists():
                return False
        return True

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
