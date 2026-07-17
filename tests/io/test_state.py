"""Tests for the state management module."""

import pytest

from anappt.io.state import (
    StageStatus,
    StateManager,
    create_initial_state,
)


@pytest.fixture
def state_manager(tmp_path):
    """Create a StateManager with a temp state file."""
    state_file = tmp_path / ".anappt" / "state.yaml"
    return StateManager(state_file)


class TestStageStatus:
    """Test StageStatus enum."""

    def test_enum_values(self):
        assert StageStatus.PENDING == "pending"
        assert StageStatus.IN_PROGRESS == "in_progress"
        assert StageStatus.AWAITING_REVIEW == "awaiting_review"
        assert StageStatus.COMPLETED == "completed"


class TestCreateInitialState:
    """Test initial state creation."""

    def test_initial_state_has_six_stages(self):
        state = create_initial_state("Test Project")
        assert len(state.stages) == 6
        assert state.stages[0].id == "S1"
        assert state.stages[5].id == "S6"

    def test_all_stages_pending(self):
        state = create_initial_state("Test Project")
        for stage in state.stages:
            assert stage.status == StageStatus.PENDING

    def test_current_stage_is_s1(self):
        state = create_initial_state("Test Project")
        assert state.current_stage == "S1"

    def test_project_name_set(self):
        state = create_initial_state("My Report")
        assert state.project_name == "My Report"

    def test_timestamps_set(self):
        state = create_initial_state("Test")
        assert state.created_at != ""
        assert state.updated_at != ""


class TestStateManager:
    """Test StateManager class."""

    def test_load_creates_initial_state_if_not_exists(self, tmp_path):
        state_file = tmp_path / ".anappt" / "state.yaml"
        sm = StateManager(state_file)
        assert len(sm.state.stages) == 6
        assert sm.get_current_stage().id == "S1"

    def test_save_and_reload(self, tmp_path):
        state_file = tmp_path / ".anappt" / "state.yaml"
        sm = StateManager(state_file)
        sm.transition("S1", StageStatus.IN_PROGRESS)
        sm.save()

        # Reload
        sm2 = StateManager(state_file)
        assert sm2.get_stage("S1").status == StageStatus.IN_PROGRESS

    def test_get_stage_returns_correct_stage(self, state_manager):
        stage = state_manager.get_stage("S3")
        assert stage is not None
        assert stage.id == "S3"
        assert stage.status == StageStatus.PENDING

    def test_get_stage_returns_none_for_invalid(self, state_manager):
        assert state_manager.get_stage("S9") is None

    def test_get_current_stage(self, state_manager):
        current = state_manager.get_current_stage()
        assert current.id == "S1"

    def test_can_start_s1_no_prerequisites(self, state_manager):
        assert state_manager.can_start("S1") is True

    def test_cannot_start_s2_when_s1_pending(self, state_manager):
        assert state_manager.can_start("S2") is False

    def test_cannot_start_s2_when_s1_in_progress(self, state_manager):
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        assert state_manager.can_start("S2") is False

    def test_cannot_start_s2_when_s1_awaiting_review(self, state_manager):
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        state_manager.transition("S1", StageStatus.AWAITING_REVIEW)
        assert state_manager.can_start("S2") is False

    def test_can_start_s2_when_s1_completed(self, state_manager):
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        state_manager.transition("S1", StageStatus.AWAITING_REVIEW)
        state_manager.transition("S1", StageStatus.COMPLETED)
        assert state_manager.can_start("S2") is True

    def test_cannot_start_completed_stage(self, state_manager):
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        state_manager.transition("S1", StageStatus.AWAITING_REVIEW)
        state_manager.transition("S1", StageStatus.COMPLETED)
        assert state_manager.can_start("S1") is False

    def test_transition_pending_to_in_progress(self, state_manager):
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        stage = state_manager.get_stage("S1")
        assert stage.status == StageStatus.IN_PROGRESS
        assert stage.started_at is not None

    def test_transition_in_progress_to_awaiting_review(self, state_manager):
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        state_manager.transition("S1", StageStatus.AWAITING_REVIEW)
        assert state_manager.get_stage("S1").status == StageStatus.AWAITING_REVIEW

    def test_transition_awaiting_review_to_completed(self, state_manager):
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        state_manager.transition("S1", StageStatus.AWAITING_REVIEW)
        state_manager.transition("S1", StageStatus.COMPLETED)
        stage = state_manager.get_stage("S1")
        assert stage.status == StageStatus.COMPLETED
        assert stage.completed_at is not None

    def test_review_to_in_progress_increments_iteration(self, state_manager):
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        state_manager.transition("S1", StageStatus.AWAITING_REVIEW)
        assert state_manager.get_stage("S1").iteration == 0

        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        assert state_manager.get_stage("S1").iteration == 1

        state_manager.transition("S1", StageStatus.AWAITING_REVIEW)
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        assert state_manager.get_stage("S1").iteration == 2

    def test_invalid_transition_pending_to_completed_raises(self, state_manager):
        with pytest.raises(ValueError, match="Invalid transition"):
            state_manager.transition("S1", StageStatus.COMPLETED)

    def test_invalid_transition_completed_to_in_progress_raises(self, state_manager):
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        state_manager.transition("S1", StageStatus.AWAITING_REVIEW)
        state_manager.transition("S1", StageStatus.COMPLETED)
        with pytest.raises(ValueError, match="Invalid transition"):
            state_manager.transition("S1", StageStatus.IN_PROGRESS)

    def test_transition_to_invalid_stage_raises(self, state_manager):
        with pytest.raises(ValueError, match="Invalid stage ID"):
            state_manager.transition("S9", StageStatus.IN_PROGRESS)

    def test_transition_skipping_prerequisites_raises(self, state_manager):
        with pytest.raises(ValueError, match="Prerequisites not met"):
            state_manager.transition("S2", StageStatus.IN_PROGRESS)

    def test_completed_advances_current_stage(self, state_manager):
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        state_manager.transition("S1", StageStatus.AWAITING_REVIEW)
        state_manager.transition("S1", StageStatus.COMPLETED)
        assert state_manager.state.current_stage == "S2"

    def test_reset_all_stages_to_pending(self, state_manager):
        # Progress through some stages
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        state_manager.transition("S1", StageStatus.AWAITING_REVIEW)
        state_manager.transition("S1", StageStatus.COMPLETED)
        state_manager.transition("S2", StageStatus.IN_PROGRESS)

        state_manager.reset()

        for stage in state_manager.state.stages:
            assert stage.status == StageStatus.PENDING
            assert stage.started_at is None
            assert stage.completed_at is None
            assert stage.iteration == 0
        assert state_manager.state.current_stage == "S1"

    def test_is_pipeline_complete_false_initially(self, state_manager):
        assert state_manager.is_pipeline_complete() is False

    def test_is_pipeline_complete_true_when_all_done(self, state_manager):
        for stage_id in ["S1", "S2", "S3", "S4", "S5", "S6"]:
            state_manager.transition(stage_id, StageStatus.IN_PROGRESS)
            state_manager.transition(stage_id, StageStatus.AWAITING_REVIEW)
            state_manager.transition(stage_id, StageStatus.COMPLETED)
        assert state_manager.is_pipeline_complete() is True

    def test_get_all_stages(self, state_manager):
        stages = state_manager.get_all_stages()
        assert len(stages) == 6
        assert stages[0].id == "S1"
        assert stages[5].id == "S6"

    def test_started_at_set_on_first_in_progress_only(self, state_manager):
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        first_started = state_manager.get_stage("S1").started_at
        assert first_started is not None

        state_manager.transition("S1", StageStatus.AWAITING_REVIEW)
        state_manager.transition("S1", StageStatus.IN_PROGRESS)
        second_started = state_manager.get_stage("S1").started_at
        assert second_started == first_started  # Should not change on re-entry
