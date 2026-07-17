"""Pipeline state management for AnaPPTAgent.

Defines the six-stage gated state machine and provides persistence
through YAML state files.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class StageStatus(StrEnum):
    """Possible statuses for a pipeline stage."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"


class StageState(BaseModel):
    """State of a single pipeline stage."""

    id: str
    name: str
    status: StageStatus = StageStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    iteration: int = 0


class PipelineState(BaseModel):
    """Complete pipeline state for a project."""

    project_name: str = ""
    created_at: str = ""
    updated_at: str = ""
    current_stage: str = "S1"
    stages: list[StageState] = Field(default_factory=list)


# Stage definitions: id -> name
STAGE_DEFINITIONS: list[tuple[str, str]] = [
    ("S1", "stage.s1.name"),
    ("S2", "stage.s2.name"),
    ("S3", "stage.s3.name"),
    ("S4", "stage.s4.name"),
    ("S5", "stage.s5.name"),
    ("S6", "stage.s6.name"),
]

# Prerequisite map: stage_id -> list of stage_ids that must be completed first
STAGE_PREREQUISITES: dict[str, list[str]] = {
    "S1": [],
    "S2": ["S1"],
    "S3": ["S2"],
    "S4": ["S3"],
    "S5": ["S4"],
    "S6": ["S5"],
}

# Valid transitions: current_status -> set of allowed target statuses
VALID_TRANSITIONS: dict[StageStatus, set[StageStatus]] = {
    StageStatus.PENDING: {StageStatus.IN_PROGRESS},
    StageStatus.IN_PROGRESS: {StageStatus.AWAITING_REVIEW},
    StageStatus.AWAITING_REVIEW: {StageStatus.COMPLETED, StageStatus.IN_PROGRESS},
    StageStatus.COMPLETED: set(),  # terminal state, no further transitions
}


def _now_iso() -> str:
    """Return current timestamp in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


def create_initial_state(project_name: str = "") -> PipelineState:
    """Create a fresh pipeline state with all stages pending.

    Args:
        project_name: Name of the project.

    Returns:
        PipelineState with all six stages in pending status.
    """
    now = _now_iso()
    stages = [
        StageState(id=sid, name=name_key, status=StageStatus.PENDING)
        for sid, name_key in STAGE_DEFINITIONS
    ]
    return PipelineState(
        project_name=project_name,
        created_at=now,
        updated_at=now,
        current_stage="S1",
        stages=stages,
    )


class StateManager:
    """Manages pipeline state persistence and transitions.

    Reads from and writes to a YAML state file in the project's .anappt directory.
    """

    def __init__(self, state_file: str | Path) -> None:
        """Initialize the state manager.

        Args:
            state_file: Path to the state.yaml file.
        """
        self.state_file = Path(state_file)
        self.state: PipelineState = self._load()

    def _load(self) -> PipelineState:
        """Load state from the state file, or create initial state if not found."""
        if not self.state_file.exists():
            return create_initial_state()
        with open(self.state_file, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        # Convert status strings to StageStatus enum
        stages_data = raw.get("stages", [])
        for stage_data in stages_data:
            if isinstance(stage_data.get("status"), str):
                stage_data["status"] = StageStatus(stage_data["status"])
        return PipelineState.model_validate(raw)

    def save(self) -> None:
        """Persist current state to the state file."""
        self.state.updated_at = _now_iso()
        # Ensure parent directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = self.state.model_dump(mode="json")
        with open(self.state_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def get_stage(self, stage_id: str) -> StageState | None:
        """Get the state of a specific stage by ID.

        Args:
            stage_id: Stage identifier (e.g., 'S1').

        Returns:
            StageState if found, None otherwise.
        """
        for stage in self.state.stages:
            if stage.id == stage_id:
                return stage
        return None

    def get_current_stage(self) -> StageState | None:
        """Get the current active stage.

        Returns:
            StageState for the current stage, or None if pipeline is complete.
        """
        return self.get_stage(self.state.current_stage)

    def can_start(self, stage_id: str) -> bool:
        """Check if a stage can be started (prerequisites met).

        A stage can start if all its prerequisite stages are completed
        and the stage itself is in 'pending' status.

        Args:
            stage_id: Stage identifier.

        Returns:
            True if the stage can be started.
        """
        stage = self.get_stage(stage_id)
        if stage is None:
            return False
        if stage.status != StageStatus.PENDING:
            return False
        for prereq_id in STAGE_PREREQUISITES.get(stage_id, []):
            prereq = self.get_stage(prereq_id)
            if prereq is None or prereq.status != StageStatus.COMPLETED:
                return False
        return True

    def transition(self, stage_id: str, target_status: StageStatus) -> bool:
        """Transition a stage to a new status.

        Validates that the transition is allowed by the state machine rules
        and that prerequisites are met for starting a stage.

        Args:
            stage_id: Stage identifier.
            target_status: Target status.

        Returns:
            True if transition was successful.

        Raises:
            ValueError: If the transition is invalid.
        """
        stage = self.get_stage(stage_id)
        if stage is None:
            raise ValueError(f"Invalid stage ID: {stage_id}")

        current = stage.status
        allowed = VALID_TRANSITIONS.get(current, set())
        if target_status not in allowed:
            raise ValueError(
                f"Invalid transition: {current.value} -> {target_status.value} for stage {stage_id}"
            )

        # Check prerequisites when starting a stage
        if target_status == StageStatus.IN_PROGRESS and current == StageStatus.PENDING:
            if not self.can_start(stage_id):
                raise ValueError(f"Prerequisites not met for stage {stage_id}")

        stage.status = target_status
        if target_status == StageStatus.IN_PROGRESS:
            if stage.started_at is None:
                stage.started_at = _now_iso()
            if current == StageStatus.AWAITING_REVIEW:
                stage.iteration += 1
        elif target_status == StageStatus.COMPLETED:
            stage.completed_at = _now_iso()

        # Update current stage pointer
        if target_status == StageStatus.COMPLETED:
            self._advance_current_stage(stage_id)

        self.save()
        return True

    def _advance_current_stage(self, completed_stage_id: str) -> None:
        """Move the current_stage pointer to the next pending stage.

        Args:
            completed_stage_id: The stage that was just completed.
        """
        stage_ids = [s[0] for s in STAGE_DEFINITIONS]
        try:
            idx = stage_ids.index(completed_stage_id)
        except ValueError:
            return
        if idx + 1 < len(stage_ids):
            self.state.current_stage = stage_ids[idx + 1]

    def reset(self) -> None:
        """Reset all stages to pending status.

        Used for the --from-scratch option.
        """
        now = _now_iso()
        for stage in self.state.stages:
            stage.status = StageStatus.PENDING
            stage.started_at = None
            stage.completed_at = None
            stage.iteration = 0
        self.state.current_stage = "S1"
        self.state.updated_at = now
        self.save()

    def get_all_stages(self) -> list[StageState]:
        """Return all stage states in order.

        Returns:
            List of all StageState objects.
        """
        return list(self.state.stages)

    def is_pipeline_complete(self) -> bool:
        """Check if all stages are completed.

        Returns:
            True if all stages have completed status.
        """
        return all(s.status == StageStatus.COMPLETED for s in self.state.stages)

    def get_stage_name(self, stage_id: str) -> str | None:
        """Get the i18n key for a stage's display name.

        Args:
            stage_id: Stage identifier.

        Returns:
            i18n key string for the stage name, or None if not found.
        """
        stage = self.get_stage(stage_id)
        if stage is not None:
            return stage.name
        return None
