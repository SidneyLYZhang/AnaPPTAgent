"""Pipeline orchestrator for AnaPPTAgent.

Manages the six-stage gated pipeline: starting, running, confirming,
revising, and resetting stages. Integrates with StateManager for
persistence and GitAutoCommit for automatic version control.
"""

from __future__ import annotations

from typing import Any

from anappt.i18n import t
from anappt.io.state import StageStatus
from anappt.stage_base import StageBase
from anappt.types import PipelineContext


class Orchestrator:
    """Coordinates the six-stage pipeline execution.

    The orchestrator:
    1. Registers all stages (S1-S6)
    2. Manages stage transitions (pending → in_progress → awaiting_review → completed)
    3. Handles user confirmation and revision feedback
    4. Triggers Git auto-commits at three key points
    5. Logs conversations to session history

    Attributes:
        stages: Ordered dict of stage_id → StageBase instances.
        ctx: Pipeline context (set when pipeline is initialized).
    """

    def __init__(self) -> None:
        """Initialize an empty orchestrator."""
        self.stages: dict[str, StageBase] = {}
        self.ctx: PipelineContext | None = None

    def register_stage(self, stage: StageBase) -> None:
        """Register a stage with the orchestrator.

        Args:
            stage: StageBase instance to register.
        """
        self.stages[stage.stage_id] = stage

    def register_stages(self, stages: list[StageBase]) -> None:
        """Register multiple stages at once.

        Args:
            stages: List of StageBase instances.
        """
        for stage in stages:
            self.register_stage(stage)

    def set_context(self, ctx: PipelineContext) -> None:
        """Set the pipeline context for the orchestrator.

        Args:
            ctx: Pipeline context with all services.
        """
        self.ctx = ctx

    def _ensure_context(self) -> PipelineContext:
        """Ensure context is set, raising if not.

        Returns:
            The pipeline context.

        Raises:
            RuntimeError: If context has not been set.
        """
        if self.ctx is None:
            raise RuntimeError("Pipeline context not set. Call set_context() first.")
        return self.ctx

    def run(self) -> dict[str, Any]:
        """Run the pipeline from the current stage.

        Executes stages sequentially from the current stage until a stage
        reaches awaiting_review (requires user confirmation) or all complete.

        Returns:
            Dictionary with 'completed' (bool), 'stage_id' (str|None),
            'summary' (str), and 'artifacts' (list[str]).

        Raises:
            RuntimeError: If context is not set or no stages registered.
        """
        ctx = self._ensure_context()
        if not self.stages:
            raise RuntimeError(t("orchestrator.no_stages"))

        state = ctx.state

        # Check if already complete
        if state.is_pipeline_complete():
            self._log_ui(ctx, t("orchestrator.already_complete"))
            return {
                "completed": True,
                "stage_id": None,
                "summary": t("orchestrator.already_complete"),
                "artifacts": [],
            }

        while not state.is_pipeline_complete():
            current_stage_id = state.state.current_stage
            stage = self.stages.get(current_stage_id)
            if stage is None:
                break

            current = state.get_stage(current_stage_id)
            if current is None:
                break

            # If stage is awaiting_review, stop and wait for user
            if current.status == StageStatus.AWAITING_REVIEW:
                return {
                    "completed": False,
                    "stage_id": current_stage_id,
                    "summary": current.name,
                    "artifacts": stage.get_artifacts(ctx),
                }

            # If stage is completed, skip to next
            if current.status == StageStatus.COMPLETED:
                continue

            # If stage is pending, validate prerequisites and run
            if current.status == StageStatus.PENDING:
                if not stage.validate_prerequisites(state):
                    prereq = t("error.prerequisite_not_met", stage_id=current_stage_id)
                    return {
                        "completed": False,
                        "stage_id": current_stage_id,
                        "summary": prereq,
                        "artifacts": [],
                    }

            # Run the stage
            output = self._run_stage(stage, ctx)
            if not output.success:
                error_msg = t(
                    "orchestrator.stage_failed",
                    stage_id=current_stage_id,
                    error=output.summary,
                )
                self._log_ui(ctx, error_msg)
                return {
                    "completed": False,
                    "stage_id": current_stage_id,
                    "summary": output.summary,
                    "artifacts": output.artifacts,
                }

            # Transition to awaiting_review
            state.transition(current_stage_id, StageStatus.AWAITING_REVIEW)

            # Git commit on stage complete
            self._git_commit_stage(ctx, current_stage_id, stage.display_name(), output.artifacts)

            # Stop and wait for user confirmation
            self._log_ui(ctx, t("orchestrator.stage_completed", stage_id=current_stage_id))
            self._log_ui(ctx, t("cli.stage_output", summary=output.summary))
            return {
                "completed": False,
                "stage_id": current_stage_id,
                "summary": output.summary,
                "artifacts": output.artifacts,
            }

        # All stages complete
        self._log_ui(ctx, t("orchestrator.pipeline_complete"))
        self._git_commit_exit(ctx)
        return {
            "completed": True,
            "stage_id": None,
            "summary": t("orchestrator.pipeline_complete"),
            "artifacts": [],
        }

    def _run_stage(self, stage: StageBase, ctx: PipelineContext) -> Any:
        """Run a single stage, handling state transitions and session logging.

        Args:
            stage: The stage to run.
            ctx: Pipeline context.

        Returns:
            StageOutput from the stage.
        """
        state = ctx.state

        # Start session logging
        if ctx.session is not None:
            ctx.session.new_session(stage.stage_id)

        # Transition to in_progress
        state.transition(stage.stage_id, StageStatus.IN_PROGRESS)
        display = stage.display_name()
        self._log_ui(
            ctx,
            t(
                "orchestrator.starting_stage",
                stage_id=stage.stage_id,
                stage_name=display,
            ),
        )

        # Execute the stage
        output = stage.run(ctx)

        # Flush session log
        if ctx.session is not None:
            ctx.session.flush()

        return output

    def confirm(self) -> dict[str, Any]:
        """Confirm the current awaiting_review stage and advance.

        Returns:
            Dictionary with 'confirmed' (bool), 'stage_id' (str|None),
            and 'next_stage' (str|None).
        """
        ctx = self._ensure_context()
        state = ctx.state

        current_stage_id = state.state.current_stage
        current = state.get_stage(current_stage_id)

        if current is None or current.status != StageStatus.AWAITING_REVIEW:
            return {
                "confirmed": False,
                "stage_id": current_stage_id,
                "next_stage": None,
            }

        stage = self.stages.get(current_stage_id)
        stage_name = stage.display_name() if stage else current_stage_id

        # Transition to completed
        state.transition(current_stage_id, StageStatus.COMPLETED)

        # Git commit on confirm
        self._git_commit_confirm(ctx, current_stage_id, stage_name)

        # Check if pipeline is complete
        if state.is_pipeline_complete():
            self._log_ui(ctx, t("orchestrator.pipeline_complete"))
            self._git_commit_exit(ctx)
            return {
                "confirmed": True,
                "stage_id": current_stage_id,
                "next_stage": None,
            }

        # Continue running from the next stage
        result = self.run()
        return {
            "confirmed": True,
            "stage_id": current_stage_id,
            "next_stage": result.get("stage_id"),
        }

    def revise(self, feedback: str) -> dict[str, Any]:
        """Revise the current stage based on user feedback.

        Transitions the stage back to in_progress and re-runs it.

        Args:
            feedback: User's revision feedback.

        Returns:
            Dictionary with 'revised' (bool), 'stage_id' (str|None),
            'summary' (str), and 'artifacts' (list[str]).
        """
        ctx = self._ensure_context()
        state = ctx.state

        current_stage_id = state.state.current_stage
        current = state.get_stage(current_stage_id)

        if current is None or current.status != StageStatus.AWAITING_REVIEW:
            return {
                "revised": False,
                "stage_id": current_stage_id,
                "summary": "",
                "artifacts": [],
            }

        stage = self.stages.get(current_stage_id)
        if stage is None:
            return {
                "revised": False,
                "stage_id": current_stage_id,
                "summary": "",
                "artifacts": [],
            }

        # Log user feedback
        if ctx.session is not None:
            ctx.session.log_user(feedback)

        # Transition back to in_progress
        state.transition(current_stage_id, StageStatus.IN_PROGRESS)
        self._log_ui(ctx, t("gate.revising"))

        # Re-run the stage
        output = stage.run(ctx)

        # Flush session log
        if ctx.session is not None:
            ctx.session.flush()

        # Transition to awaiting_review again
        state.transition(current_stage_id, StageStatus.AWAITING_REVIEW)

        # Git commit on stage complete
        self._git_commit_stage(ctx, current_stage_id, stage.display_name(), output.artifacts)

        self._log_ui(ctx, t("orchestrator.stage_completed", stage_id=current_stage_id))
        self._log_ui(ctx, t("cli.stage_output", summary=output.summary))

        return {
            "revised": True,
            "stage_id": current_stage_id,
            "summary": output.summary,
            "artifacts": output.artifacts,
        }

    def resume(self) -> dict[str, Any]:
        """Resume the pipeline from the current state.

        Returns:
            Same as run() result.
        """
        ctx = self._ensure_context()
        current_stage_id = ctx.state.state.current_stage
        self._log_ui(ctx, t("orchestrator.resuming", stage_id=current_stage_id))
        return self.run()

    def reset(self) -> dict[str, Any]:
        """Reset all stages to pending status.

        Returns:
            Dictionary with 'reset' (bool).
        """
        ctx = self._ensure_context()
        self._log_ui(ctx, t("orchestrator.resetting"))
        ctx.state.reset()
        return {"reset": True}

    def get_status(self) -> list[dict[str, Any]]:
        """Get the status of all stages.

        Returns:
            List of dicts with 'id', 'name', 'status', 'iteration' per stage.
        """
        ctx = self._ensure_context()
        stages = ctx.state.get_all_stages()
        result: list[dict[str, Any]] = []
        for stage in stages:
            stage_obj = self.stages.get(stage.id)
            display_name = stage_obj.display_name() if stage_obj else stage.name
            result.append(
                {
                    "id": stage.id,
                    "name": display_name,
                    "status": stage.status.value,
                    "iteration": stage.iteration,
                    "started_at": stage.started_at,
                    "completed_at": stage.completed_at,
                }
            )
        return result

    def _log_ui(self, ctx: PipelineContext, message: str) -> None:
        """Print a message to the UI if available.

        Args:
            ctx: Pipeline context.
            message: Message to display.
        """
        if ctx.ui is not None:
            ctx.ui.print(message)

    def _git_commit_stage(
        self,
        ctx: PipelineContext,
        stage_id: str,
        stage_name: str,
        files: list[str],
    ) -> None:
        """Trigger git commit on stage completion.

        Args:
            ctx: Pipeline context.
            stage_id: Stage identifier.
            stage_name: Stage display name.
            files: List of artifact file paths.
        """
        if ctx.git is not None:
            ctx.git.commit_on_stage_complete(stage_id, stage_name, files)

    def _git_commit_confirm(
        self, ctx: PipelineContext, stage_id: str, stage_name: str
    ) -> None:
        """Trigger git commit on user confirmation.

        Args:
            ctx: Pipeline context.
            stage_id: Stage identifier.
            stage_name: Stage display name.
        """
        if ctx.git is not None:
            ctx.git.commit_on_confirm(stage_id, stage_name)

    def _git_commit_exit(self, ctx: PipelineContext) -> None:
        """Trigger git commit on pipeline exit.

        Args:
            ctx: Pipeline context.
        """
        if ctx.git is not None:
            ctx.git.commit_on_exit()
