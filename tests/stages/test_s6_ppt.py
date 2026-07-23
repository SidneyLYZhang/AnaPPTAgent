"""Tests for S6PPTStage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anappt.io.config import DeliveryInfo, ProjectInfo, ReportConfig
from anappt.io.state import StateManager
from anappt.stages.s6_ppt import S6PPTStage
from anappt.types import PipelineContext

VALID_GOAL_JSON = (
    '{"title":"Test","goal":"...","audience":[],"owner":"test",'
    '"randomSeed":42,"pageCount":5,"themePack":"theme03","slides":[]}'
)


@pytest.fixture
def skill_root(tmp_path: Path) -> Path:
    """Create a fake dashi-ppt skill root with SKILL.md and render scripts."""
    skill = tmp_path / "dashi-ppt"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text("# dashi-ppt-skill\n\nskill doc", encoding="utf-8")
    scripts_dir = skill / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "render_goal_deck.ps1").write_text("", encoding="utf-8")
    (scripts_dir / "render_goal_deck.sh").write_text("", encoding="utf-8")
    return skill


@pytest.fixture
def mock_skill_manager(skill_root: Path) -> MagicMock:
    """Return a mock SkillManager pointing at the fixture skill_root."""
    sm = MagicMock()
    sm.locate_skill.return_value = str(skill_root / "SKILL.md")
    return sm


@pytest.fixture
def config() -> ReportConfig:
    """Return a ReportConfig with delivery settings."""
    return ReportConfig(
        project=ProjectInfo(name="test_project"),
        delivery=DeliveryInfo(
            ppt_pages="15-20",
            formats=["pptx", "html"],
            theme_preference="theme03",
        ),
    )


@pytest.fixture
def ctx(
    tmp_path: Path,
    config: ReportConfig,
    mock_skill_manager: MagicMock,
) -> PipelineContext:
    """Return a PipelineContext wired with a mock skill_manager."""
    llm = MagicMock()
    llm.chat.return_value = VALID_GOAL_JSON
    ui = MagicMock()
    ui.input.return_value = "theme02"
    state = StateManager(tmp_path / ".anappt" / "state.yaml")
    ctx = PipelineContext(
        project_dir=tmp_path,
        config=config,
        llm=llm,
        state=state,
        ui=ui,
        skill_manager=mock_skill_manager,
    )
    # S6 reads output/final_report.md first, falling back to report.md
    ctx.get_artifact_path("final_report.md").write_text(
        "# Report\n\nContent", encoding="utf-8"
    )
    return ctx


class TestS6Attributes:
    """Tests for stage attributes."""

    def test_stage_id(self) -> None:
        assert S6PPTStage().stage_id == "S6"

    def test_stage_name(self) -> None:
        assert S6PPTStage().stage_name == "stage.s6.name"

    def test_model_role(self) -> None:
        assert S6PPTStage().model_role == "writing"


class TestS6Prerequisites:
    """Tests for validate_prerequisites."""

    def test_requires_s5_completed(self, tmp_path: Path) -> None:
        from anappt.io.state import StageStatus

        state = StateManager(tmp_path / "state.yaml")
        stage = S6PPTStage()

        assert stage.validate_prerequisites(state) is False

        for sid in ["S1", "S2", "S3", "S4", "S5"]:
            state.transition(sid, StageStatus.IN_PROGRESS)
            state.transition(sid, StageStatus.AWAITING_REVIEW)
            state.transition(sid, StageStatus.COMPLETED)

        assert stage.validate_prerequisites(state) is True


class TestS6RunWorkflow:
    """Tests for the new 7-step workflow."""

    # ===== Step 1: skill_manager / locate_skill checks =====

    def test_step1_skill_manager_none_returns_failure(
        self, tmp_path: Path, config: ReportConfig
    ) -> None:
        llm = MagicMock()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=config,
            llm=llm,
            state=state,
            skill_manager=None,
        )
        ctx.get_artifact_path("final_report.md").write_text("# x", encoding="utf-8")

        stage = S6PPTStage()
        output = stage.run(ctx)

        assert output.success is False
        assert output.next_action == "retry"

    def test_step1_skill_not_installed_returns_failure(
        self, tmp_path: Path, config: ReportConfig
    ) -> None:
        sm = MagicMock()
        sm.locate_skill.return_value = None
        llm = MagicMock()
        state = StateManager(tmp_path / ".anappt" / "state.yaml")
        ctx = PipelineContext(
            project_dir=tmp_path,
            config=config,
            llm=llm,
            state=state,
            skill_manager=sm,
        )
        ctx.get_artifact_path("final_report.md").write_text("# x", encoding="utf-8")

        stage = S6PPTStage()
        output = stage.run(ctx)

        assert output.success is False
        assert output.next_action == "retry"

    # ===== Step 2: load SKILL.md =====

    def test_step2_skill_md_missing_returns_failure(
        self, ctx: PipelineContext
    ) -> None:
        stage = S6PPTStage()
        with patch(
            "anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md",
            side_effect=FileNotFoundError("SKILL.md missing"),
        ):
            output = stage.run(ctx)

        assert output.success is False
        assert output.next_action == "retry"

    # ===== Steps 3-4: theme selection + goal.json construction =====

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_step3_4_goal_json_written_correctly(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        ctx: PipelineContext,
    ) -> None:
        mock_load.return_value = "# fake skill"
        ctx.config.delivery.formats = []  # skip pptx export
        ctx.llm.chat.return_value = VALID_GOAL_JSON

        stage = S6PPTStage()
        output = stage.run(ctx)

        assert output.success is True
        goal_path = ctx.get_artifact_path("ppt") / "goal.json"
        assert goal_path.exists()
        content = goal_path.read_text(encoding="utf-8")
        assert "title" in content
        assert "theme03" in content

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_step3_4_goal_json_parse_failure_returns_failure(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        ctx: PipelineContext,
    ) -> None:
        mock_load.return_value = "# fake skill"
        ctx.llm.chat.return_value = "invalid json"

        stage = S6PPTStage()
        output = stage.run(ctx)

        assert output.success is False
        assert output.next_action == "retry"

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_step3_theme_preference_set_skips_llm_selection(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        ctx: PipelineContext,
    ) -> None:
        mock_load.return_value = "# fake skill"
        ctx.config.delivery.theme_preference = "theme05"
        ctx.config.delivery.formats = []  # skip pptx export
        ctx.llm.chat.return_value = VALID_GOAL_JSON

        stage = S6PPTStage()
        stage.run(ctx)

        # theme_preference set => only goal.json LLM call, no theme_selection call
        assert ctx.llm.chat.call_count == 1

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_step3_no_theme_preference_calls_llm_and_input(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        ctx: PipelineContext,
    ) -> None:
        mock_load.return_value = "# fake skill"
        ctx.config.delivery.theme_preference = None
        ctx.config.delivery.formats = []  # skip pptx export
        ctx.llm.chat.side_effect = [
            "Theme list:\n1. theme01 - ...",  # theme_selection response
            VALID_GOAL_JSON.replace('"theme03"', '"theme02"'),  # goal.json
        ]
        ctx.ui.input.return_value = "theme02"

        stage = S6PPTStage()
        stage.run(ctx)

        assert ctx.llm.chat.call_count == 2
        assert ctx.ui.input.call_count == 1
        goal_path = ctx.get_artifact_path("ppt") / "goal.json"
        content = goal_path.read_text(encoding="utf-8")
        assert "theme02" in content

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_step3_invalid_user_input_falls_back_to_theme01(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        ctx: PipelineContext,
    ) -> None:
        mock_load.return_value = "# fake skill"
        ctx.config.delivery.theme_preference = None
        ctx.config.delivery.formats = []  # skip pptx export
        ctx.llm.chat.side_effect = [
            "Theme list:\n1. theme01 - ...",  # theme_selection response
            VALID_GOAL_JSON,  # goal.json content (irrelevant for assertion)
        ]
        ctx.ui.input.return_value = "garbage"

        stage = S6PPTStage()
        stage.run(ctx)

        # Verify the fallback: the goal.json prompt should use themePack: theme01
        last_call = ctx.llm.chat.call_args_list[-1]
        user_msg = last_call.kwargs["messages"][-1]["content"]
        assert "themePack: theme01" in user_msg

    # ===== Step 5: render_deck =====

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_step5_render_deck_called_with_correct_args(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        ctx: PipelineContext,
    ) -> None:
        mock_load.return_value = "# fake skill"
        ctx.config.delivery.formats = []  # skip pptx export
        ctx.llm.chat.return_value = VALID_GOAL_JSON

        stage = S6PPTStage()
        stage.run(ctx)

        assert mock_render.called
        kwargs = mock_render.call_args.kwargs
        assert "goal_json_path" in kwargs
        assert "output_html_path" in kwargs
        assert "skill_root" in kwargs

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_step5_render_failure_returns_failure(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        ctx: PipelineContext,
    ) -> None:
        mock_load.return_value = "# fake skill"
        ctx.llm.chat.return_value = VALID_GOAL_JSON
        mock_render.side_effect = RuntimeError("render failed")

        stage = S6PPTStage()
        output = stage.run(ctx)

        assert output.success is False
        assert output.next_action == "retry"

    # ===== Step 7: PPTX export (optional, before step 6) =====

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.export")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_step7_pptx_in_formats_triggers_export(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        mock_export: MagicMock,
        ctx: PipelineContext,
    ) -> None:
        mock_load.return_value = "# fake skill"
        ctx.config.delivery.formats = ["pptx", "html"]
        ctx.llm.chat.return_value = VALID_GOAL_JSON

        stage = S6PPTStage()
        output = stage.run(ctx)

        assert mock_export.called
        assert any("presentation.pptx" in p for p in output.artifacts)

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.export")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_step7_no_pptx_in_formats_skips_export(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        mock_export: MagicMock,
        ctx: PipelineContext,
    ) -> None:
        mock_load.return_value = "# fake skill"
        ctx.config.delivery.formats = ["html"]
        ctx.llm.chat.return_value = VALID_GOAL_JSON

        stage = S6PPTStage()
        stage.run(ctx)

        assert not mock_export.called

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.export")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_step7_export_failure_does_not_block_success(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        mock_export: MagicMock,
        ctx: PipelineContext,
    ) -> None:
        mock_load.return_value = "# fake skill"
        ctx.config.delivery.formats = ["pptx"]
        ctx.llm.chat.return_value = VALID_GOAL_JSON
        mock_export.side_effect = RuntimeError("export failed")

        stage = S6PPTStage()
        output = stage.run(ctx)

        # Export failure only emits a warning; stage still succeeds
        assert output.success is True

    # ===== Step 6: return awaiting_review =====

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.export")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_step6_returns_awaiting_review_next_action(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        mock_export: MagicMock,
        ctx: PipelineContext,
    ) -> None:
        mock_load.return_value = "# fake skill"
        ctx.config.delivery.formats = []  # skip pptx export
        ctx.llm.chat.return_value = VALID_GOAL_JSON

        stage = S6PPTStage()
        output = stage.run(ctx)

        assert output.success is True
        assert output.next_action == "confirm"
        assert any("index.html" in p for p in output.artifacts)

    # ===== SubTask 7.3: S6 must NOT trigger skill download =====

    @patch("anappt.stages.s6_ppt.DashiPPTBridge.export")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.render_deck")
    @patch("anappt.stages.s6_ppt.DashiPPTBridge.load_skill_md")
    def test_s6_does_not_trigger_install_or_update_skill(
        self,
        mock_load: MagicMock,
        mock_render: MagicMock,
        mock_export: MagicMock,
        ctx: PipelineContext,
        mock_skill_manager: MagicMock,
    ) -> None:
        """S6 整个 run 过程中 install_or_update_skill 必须从未被调用。

        S6 应通过 locate_skill() 定位已安装的 skill;若未安装应直接返回
        失败,绝不在运行时触发下载(下载职责属于 anappt setup / anappt new)。
        """
        mock_load.return_value = "# fake skill"
        ctx.config.delivery.formats = []  # skip pptx export
        ctx.llm.chat.return_value = VALID_GOAL_JSON

        stage = S6PPTStage()
        stage.run(ctx)

        # 关键断言:整个 S6 run 流程中 SkillManager.install_or_update_skill
        # 从未被调用 (下载职责不在 S6 阶段)
        mock_skill_manager.install_or_update_skill.assert_not_called()
        # 也验证 save_skill_dir_config 未被调用 (持久化路径也不在 S6 阶段)
        mock_skill_manager.save_skill_dir_config.assert_not_called()


# ---------------------------------------------------------------------------
# Declarative metadata tests (Task B7)
# ---------------------------------------------------------------------------


def _make_empty_ctx(tmp_path: Path) -> PipelineContext:
    """Return a PipelineContext with an empty ReportConfig and no skill_manager."""
    empty_config = ReportConfig()
    state = StateManager(tmp_path / ".anappt" / "state.yaml")
    return PipelineContext(
        project_dir=tmp_path,
        config=empty_config,
        llm=MagicMock(),
        state=state,
    )


class TestS6Declarative:
    """Tests for the declarative interface added in Task B7."""

    def test_goal_is_s6_goal_key(self) -> None:
        assert S6PPTStage().goal == "s6.goal"

    def test_goal_i18n_resolves(self) -> None:
        """``s6.goal`` should resolve to a non-empty localized string."""
        from anappt.i18n import set_locale, t

        set_locale("zh")
        text = t(S6PPTStage().goal)
        assert text
        assert text != "s6.goal"  # not a missing-key fallback

    def test_get_artifacts_returns_goal_json_and_html(
        self, tmp_path: Path
    ) -> None:
        """get_artifacts returns the expected S6 artifact paths."""
        ctx = _make_empty_ctx(tmp_path)
        artifacts = S6PPTStage().get_artifacts(ctx)
        assert "output/ppt/goal.json" in artifacts
        assert "output/ppt/presentation.html" in artifacts
        assert len(artifacts) == 2

    def test_system_prompt_fragment_nonempty(self, tmp_path: Path) -> None:
        ctx = _make_empty_ctx(tmp_path)
        fragment = S6PPTStage().system_prompt_fragment(ctx)
        assert isinstance(fragment, str)
        assert len(fragment) > 0

    def test_system_prompt_fragment_contains_key_actions(
        self, tmp_path: Path
    ) -> None:
        """The prompt must mention the key S6 actions per spec B7."""
        ctx = _make_empty_ctx(tmp_path)
        fragment = S6PPTStage().system_prompt_fragment(ctx)
        # Spec B7: construct goal.json, pick themePack, call render_deck.
        assert "goal.json" in fragment
        assert "themePack" in fragment
        assert "render_deck" in fragment
        # Must mention the artifact to render.
        assert "presentation.html" in fragment
        # Must instruct the LLM to wait for user confirm.
        assert "confirm" in fragment

    def test_system_prompt_fragment_contains_export_pptx_guidance(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_empty_ctx(tmp_path)
        fragment = S6PPTStage().system_prompt_fragment(ctx)
        assert "export_pptx" in fragment

    def test_tools_returns_expected_subset(self, tmp_path: Path) -> None:
        ctx = _make_empty_ctx(tmp_path)
        tools = S6PPTStage().tools(ctx)
        assert tools == [
            "read_file",
            "write_artifact",
            "render_deck",
            "export_pptx",
            "read_memory",
            "update_memory",
            "read_history",
        ]

    def test_is_ready_false_when_both_artifacts_missing(
        self, tmp_path: Path
    ) -> None:
        """Empty project dir → both artifacts missing → is_ready False."""
        ctx = _make_empty_ctx(tmp_path)
        assert S6PPTStage().is_ready(ctx) is False

    def test_is_ready_false_when_only_goal_json_exists(
        self, tmp_path: Path
    ) -> None:
        """Only goal.json exists, presentation.html missing → False."""
        ctx = _make_empty_ctx(tmp_path)
        ppt_dir = tmp_path / "output" / "ppt"
        ppt_dir.mkdir(parents=True, exist_ok=True)
        (ppt_dir / "goal.json").write_text('{"title":"x"}', encoding="utf-8")
        assert S6PPTStage().is_ready(ctx) is False

    def test_is_ready_false_when_only_html_exists(
        self, tmp_path: Path
    ) -> None:
        """Only presentation.html exists, goal.json missing → False."""
        ctx = _make_empty_ctx(tmp_path)
        ppt_dir = tmp_path / "output" / "ppt"
        ppt_dir.mkdir(parents=True, exist_ok=True)
        (ppt_dir / "presentation.html").write_text(
            "<html></html>", encoding="utf-8"
        )
        assert S6PPTStage().is_ready(ctx) is False

    def test_is_ready_false_when_goal_json_unparseable(
        self, tmp_path: Path
    ) -> None:
        """Both files exist but goal.json is invalid JSON → False."""
        ctx = _make_empty_ctx(tmp_path)
        ppt_dir = tmp_path / "output" / "ppt"
        ppt_dir.mkdir(parents=True, exist_ok=True)
        (ppt_dir / "goal.json").write_text(
            "{not valid json}", encoding="utf-8"
        )
        (ppt_dir / "presentation.html").write_text(
            "<html></html>", encoding="utf-8"
        )
        assert S6PPTStage().is_ready(ctx) is False

    def test_is_ready_true_when_both_artifacts_exist(
        self, tmp_path: Path
    ) -> None:
        """Both goal.json and presentation.html exist → True."""
        ctx = _make_empty_ctx(tmp_path)
        ppt_dir = tmp_path / "output" / "ppt"
        ppt_dir.mkdir(parents=True, exist_ok=True)
        (ppt_dir / "goal.json").write_text('{"title":"x"}', encoding="utf-8")
        (ppt_dir / "presentation.html").write_text(
            "<html></html>", encoding="utf-8"
        )
        assert S6PPTStage().is_ready(ctx) is True
