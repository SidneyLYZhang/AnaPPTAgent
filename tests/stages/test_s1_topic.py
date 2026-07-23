"""Tests for S1TopicStage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.io.config import ReportConfig
from anappt.io.state import StateManager
from anappt.stages.s1_topic import S1TopicStage
from anappt.types import PipelineContext


@pytest.fixture
def config() -> ReportConfig:
    """Return a ReportConfig with test data."""
    from anappt.io.config import DeliveryInfo, ProjectInfo, ReportInfo

    return ReportConfig(
        project=ProjectInfo(name="Test Project", type="one_time"),
        report=ReportInfo(
            topic="Sales Analysis Q1 2025",
            motivation="Understand Q1 sales trends",
            audience=["Management"],
            objectives=["Identify top products", "Analyze revenue trends"],
            success_criteria=["Clear actionable insights"],
        ),
        delivery=DeliveryInfo(),
    )


@pytest.fixture
def ctx(
    tmp_path: Path,
    config: ReportConfig,
) -> PipelineContext:
    """Return a PipelineContext with mock LLM."""
    llm = MagicMock()
    llm.chat.return_value = "# Refined Topic\n\nThis is the refined topic document."
    state = StateManager(tmp_path / ".anappt" / "state.yaml")
    return PipelineContext(
        project_dir=tmp_path,
        config=config,
        llm=llm,
        state=state,
    )


@pytest.fixture
def empty_ctx(tmp_path: Path) -> PipelineContext:
    """Return a PipelineContext with a fresh project dir and empty ReportConfig.

    Used by declarative tests that need to write/read report.yaml on disk
    rather than relying on the pre-populated ``config`` fixture.
    """
    from anappt.io.config import DeliveryInfo, ProjectInfo, ReportInfo

    empty_config = ReportConfig(
        project=ProjectInfo(),
        report=ReportInfo(),
        delivery=DeliveryInfo(),
    )
    state = StateManager(tmp_path / ".anappt" / "state.yaml")
    return PipelineContext(
        project_dir=tmp_path,
        config=empty_config,
        llm=MagicMock(),
        state=state,
    )


class TestS1Attributes:
    """Tests for stage attributes."""

    def test_stage_id(self) -> None:
        assert S1TopicStage().stage_id == "S1"

    def test_stage_name(self) -> None:
        assert S1TopicStage().stage_name == "stage.s1.name"

    def test_model_role(self) -> None:
        assert S1TopicStage().model_role == "reasoning"


class TestS1Run:
    """Tests for the run method."""

    def test_successful_run(self, ctx: PipelineContext) -> None:
        stage = S1TopicStage()
        output = stage.run(ctx)

        assert output.success is True
        assert len(output.artifacts) == 1
        assert "s1_topic.md" in output.artifacts[0]
        assert output.next_action == "confirm"

    def test_writes_artifact_file(self, ctx: PipelineContext) -> None:
        stage = S1TopicStage()
        stage.run(ctx)

        artifact_path = ctx.get_anappt_path("s1_topic.md")
        assert artifact_path.exists()
        content = artifact_path.read_text(encoding="utf-8")
        assert "Refined Topic" in content

    def test_llm_called_with_reasoning_role(self, ctx: PipelineContext) -> None:
        stage = S1TopicStage()
        stage.run(ctx)

        ctx.llm.chat.assert_called_once()
        call_args = ctx.llm.chat.call_args
        role = call_args[0][0] if call_args[0] else call_args.kwargs.get("role")
        assert role == "reasoning"

    def test_llm_failure(self, ctx: PipelineContext) -> None:
        ctx.llm.chat.side_effect = Exception("API error")
        stage = S1TopicStage()
        output = stage.run(ctx)

        assert output.success is False
        assert "LLM call failed" in output.summary
        assert output.next_action == "retry"

    def test_get_artifacts(self, ctx: PipelineContext) -> None:
        stage = S1TopicStage()
        artifacts = stage.get_artifacts(ctx)
        assert ".anappt/s1_topic.md" in artifacts

    def test_summary_truncated(self, ctx: PipelineContext) -> None:
        long_response = "A" * 300
        ctx.llm.chat.return_value = long_response
        stage = S1TopicStage()
        output = stage.run(ctx)
        assert len(output.summary) <= 203  # 200 + "..."


class TestS1Prerequisites:
    """Tests for validate_prerequisites."""

    def test_s1_no_prerequisites(self, tmp_path: Path) -> None:
        state = StateManager(tmp_path / "state.yaml")
        stage = S1TopicStage()
        assert stage.validate_prerequisites(state) is True


# ---------------------------------------------------------------------------
# Declarative metadata tests (Task B2)
# ---------------------------------------------------------------------------

COMPLETE_REPORT_YAML = """\
project:
  name: "Test Project"
  type: "one_time"
  created: "2026-07-22"

report:
  topic: "Q3 渠道 ROI 分析"
  motivation: "评估各渠道拉新效率"
  audience:
    - "增长团队"
    - "管理层"
  objectives:
    - "识别增长瓶颈"
    - "评估渠道 ROI"
  success_criteria:
    - "结论有数据支撑"

delivery:
  ppt_pages: "15-20"
  formats: ["pptx", "html"]
  theme_preference: null
"""

# Same shape as COMPLETE_REPORT_YAML but with required fields blanked out.
EMPTY_FIELDS_REPORT_YAML = """\
project:
  name: "Test Project"
  type: "one_time"
  created: "2026-07-22"

report:
  topic: ""
  motivation: ""
  audience: []
  objectives: []
  success_criteria: []

delivery:
  ppt_pages: "15-20"
  formats: ["pptx", "html"]
  theme_preference: null
"""

# YAML that parses as text but is structurally invalid for ReportConfig
# (e.g. report section is a string instead of a dict).
UNPARSEABLE_REPORT_YAML = """\
this: is
not: a valid report.yaml
report: "should-be-a-dict"
"""


class TestS1Declarative:
    """Tests for the declarative interface added in Task B2."""

    def test_goal_is_s1_goal_key(self) -> None:
        assert S1TopicStage().goal == "s1.goal"

    def test_goal_i18n_resolves(self) -> None:
        """``s1.goal`` should resolve to a non-empty localized string."""
        from anappt.i18n import set_locale, t

        set_locale("zh")
        text = t(S1TopicStage().goal)
        assert text
        assert text != "s1.goal"  # not a missing-key fallback

    def test_get_artifacts_returns_report_yaml_and_s1_topic(
        self, empty_ctx: PipelineContext
    ) -> None:
        artifacts = S1TopicStage().get_artifacts(empty_ctx)
        assert "report.yaml" in artifacts
        assert ".anappt/s1_topic.md" in artifacts
        assert len(artifacts) == 2

    def test_system_prompt_fragment_nonempty(
        self, empty_ctx: PipelineContext
    ) -> None:
        fragment = S1TopicStage().system_prompt_fragment(empty_ctx)
        assert isinstance(fragment, str)
        assert len(fragment) > 0

    def test_system_prompt_fragment_contains_collection_items(
        self, empty_ctx: PipelineContext
    ) -> None:
        """The prompt must mention the key collection items per spec B2."""
        fragment = S1TopicStage().system_prompt_fragment(empty_ctx)
        # Spec calls out: 受众 / 目标 / 成功标准 (and others).
        assert "受众" in fragment
        assert "目标" in fragment
        assert "成功标准" in fragment
        # Must also mention the artifacts to write.
        assert "report.yaml" in fragment
        assert "s1_topic.md" in fragment or ".anappt/s1_topic.md" in fragment
        # Must instruct the LLM to wait for user confirm.
        assert "confirm" in fragment

    def test_system_prompt_fragment_contains_write_artifact_guidance(
        self, empty_ctx: PipelineContext
    ) -> None:
        fragment = S1TopicStage().system_prompt_fragment(empty_ctx)
        assert "write_artifact" in fragment

    def test_tools_returns_expected_subset(
        self, empty_ctx: PipelineContext
    ) -> None:
        tools = S1TopicStage().tools(empty_ctx)
        assert tools == [
            "read_file",
            "write_artifact",
            "read_memory",
            "update_memory",
            "read_history",
        ]

    def test_is_ready_false_when_no_report_yaml(
        self, empty_ctx: PipelineContext
    ) -> None:
        """Empty project dir → report.yaml missing → is_ready False."""
        assert S1TopicStage().is_ready(empty_ctx) is False

    def test_is_ready_false_when_required_fields_empty(
        self, empty_ctx: PipelineContext
    ) -> None:
        """report.yaml present but topic/motivation/objectives empty → False."""
        (empty_ctx.project_dir / "report.yaml").write_text(
            EMPTY_FIELDS_REPORT_YAML, encoding="utf-8"
        )
        (empty_ctx.project_dir / ".anappt").mkdir(parents=True, exist_ok=True)
        (empty_ctx.project_dir / ".anappt" / "s1_topic.md").write_text(
            "topic doc", encoding="utf-8"
        )
        assert S1TopicStage().is_ready(empty_ctx) is False

    def test_is_ready_false_when_s1_topic_md_missing(
        self, empty_ctx: PipelineContext
    ) -> None:
        """report.yaml complete but s1_topic.md missing → False."""
        (empty_ctx.project_dir / "report.yaml").write_text(
            COMPLETE_REPORT_YAML, encoding="utf-8"
        )
        # Note: .anappt/s1_topic.md intentionally not created.
        assert S1TopicStage().is_ready(empty_ctx) is False

    def test_is_ready_false_when_report_yaml_unparseable(
        self, empty_ctx: PipelineContext
    ) -> None:
        """report.yaml present but cannot be parsed by ReportConfig → False,
        without raising."""
        (empty_ctx.project_dir / "report.yaml").write_text(
            UNPARSEABLE_REPORT_YAML, encoding="utf-8"
        )
        (empty_ctx.project_dir / ".anappt").mkdir(parents=True, exist_ok=True)
        (empty_ctx.project_dir / ".anappt" / "s1_topic.md").write_text(
            "topic doc", encoding="utf-8"
        )
        # Must not raise.
        assert S1TopicStage().is_ready(empty_ctx) is False

    def test_is_ready_true_when_complete(
        self, empty_ctx: PipelineContext
    ) -> None:
        """report.yaml parses with non-empty fields + s1_topic.md exists → True."""
        (empty_ctx.project_dir / "report.yaml").write_text(
            COMPLETE_REPORT_YAML, encoding="utf-8"
        )
        (empty_ctx.project_dir / ".anappt").mkdir(parents=True, exist_ok=True)
        (empty_ctx.project_dir / ".anappt" / "s1_topic.md").write_text(
            "# Refined topic\n\nDetailed topic document.", encoding="utf-8"
        )
        assert S1TopicStage().is_ready(empty_ctx) is True
