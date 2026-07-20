"""Stage S6: PPT Generation.

Uses the DashiPPTBridge to convert the S5 report into an HTML-based
slide presentation with theme support.
"""

from __future__ import annotations

import json
from pathlib import Path

from anappt.bridge.dashi_ppt import DashiPPTBridge
from anappt.i18n import t
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput


class S6PPTStage(StageBase):
    """Stage S6: PPT Generation.

    Implements the 7-step workflow that uses the dashi-ppt-skill as a
    real Agent skill: load SKILL.md as LLM system prompt, let the LLM
    construct goal.json, invoke the skill's render/export scripts via
    subprocess, and finally return an awaiting_review state for the
    orchestrator to handle user confirmation.
    """

    stage_id: str = "S6"
    stage_name: str = "stage.s6.name"

    def run(self, ctx: PipelineContext) -> StageOutput:
        """Execute the PPT generation stage via the 7-step workflow.

        Args:
            ctx: Pipeline context.

        Returns:
            StageOutput with the generated PPT artifacts.
        """
        # 步骤 1 前置检查 skill
        if ctx.skill_manager is None:
            print(t("s6.skill_not_installed"))
            return StageOutput(
                success=False,
                summary="SkillManager not injected",
                next_action="retry",
            )
        skill_root_path = ctx.skill_manager.locate_skill()
        if skill_root_path is None:
            print(t("s6.skill_not_installed"))
            return StageOutput(
                success=False,
                summary="dashi-ppt skill not installed",
                next_action="retry",
            )
        skill_root = Path(skill_root_path).parent

        # 步骤 2 加载 SKILL.md
        print(t("s6.loading_skill_md"))
        try:
            skill_md_text = DashiPPTBridge.load_skill_md(skill_root)
        except FileNotFoundError as e:
            return StageOutput(success=False, summary=str(e), next_action="retry")

        # 步骤 3 风格选择
        report_path = ctx.output_dir / "final_report.md"
        if not report_path.exists():
            report_path = ctx.get_artifact_path("report.md")
        report_content = (
            report_path.read_text(encoding="utf-8") if report_path.exists() else ""
        )

        theme_pack = (
            getattr(ctx.config.delivery, "theme_preference", None)
            if hasattr(ctx.config, "delivery")
            else None
        )
        if not theme_pack:
            print(t("s6.selecting_theme_pack"))
            messages = [
                {"role": "system", "content": skill_md_text},
                {"role": "user", "content": t("s6.theme_selection_prompt")},
            ]
            theme_response = ctx.llm.chat("writing", messages=messages)
            print(theme_response)
            if ctx.ui is not None:
                theme_pack = ctx.ui.input("> ").strip()
            else:
                theme_pack = "theme01"
            if not (theme_pack.startswith("theme") and theme_pack[5:7].isdigit()):
                theme_pack = "theme01"

        # 步骤 4 构造 goal.json
        print(t("s6.constructing_goal_json"))
        goal_messages = [
            {"role": "system", "content": skill_md_text},
            {
                "role": "user",
                "content": (
                    f"基于以下报告内容构造 goal.json:\n\n{report_content}\n\n"
                    f"themePack: {theme_pack}\n"
                    f"project name: {ctx.config.project.name}\n"
                    f"pageCount: {getattr(ctx.config.delivery, 'ppt_pages', 10)}"
                ),
            },
        ]
        goal_response = ctx.llm.chat("writing", messages=goal_messages)
        goal_text = goal_response.strip()
        if goal_text.startswith("```"):
            lines = goal_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            goal_text = "\n".join(lines)

        try:
            goal_data = json.loads(goal_text)
        except json.JSONDecodeError as e:
            return StageOutput(
                success=False,
                summary=t("s6.goal_json_parse_failed", error=str(e)),
                next_action="retry",
            )

        ppt_dir = ctx.output_dir / "ppt"
        ppt_dir.mkdir(parents=True, exist_ok=True)
        goal_json_path = ppt_dir / "goal.json"
        goal_json_path.write_text(
            json.dumps(goal_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 步骤 5 Bridge 渲染
        print(t("s6.rendering_deck"))
        output_html_path = ppt_dir / "ppt" / "index.html"
        try:
            DashiPPTBridge.render_deck(
                goal_json_path=goal_json_path,
                output_html_path=output_html_path,
                skill_root=skill_root,
            )
        except Exception as e:
            return StageOutput(
                success=False,
                summary=t("s6.render_failed", error=str(e)),
                next_action="retry",
            )

        # 步骤 7 导出 PPTX（可选，在步骤 6 之前执行）
        artifacts = [str(output_html_path)]
        formats = (
            getattr(ctx.config.delivery, "formats", [])
            if hasattr(ctx.config, "delivery")
            else []
        )
        if "pptx" in formats:
            print(t("s6.exporting_pptx"))
            pptx_path = ppt_dir / "presentation.pptx"
            try:
                DashiPPTBridge.export(
                    deck_dir=ppt_dir,
                    format="pptx",
                    output_file=pptx_path,
                    skill_root=skill_root,
                )
                artifacts.append(str(pptx_path))
            except Exception as e:
                print(t("s6.export_failed_warning", error=str(e)))

        # 步骤 6 用户浏览器编辑确认（返回 awaiting_review）
        preview_url = "http://127.0.0.1:5200/"
        print(t("s6.preview_url", url=preview_url))
        return StageOutput(
            success=True,
            artifacts=artifacts,
            summary=f"PPT generated with themePack={theme_pack}",
            next_action="confirm",
        )

    def get_artifacts(self, ctx: PipelineContext) -> list[str]:
        """Return the artifact paths for this stage.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing the rendered HTML and (if exported) PPTX paths.
        """
        artifacts = ["output/ppt/ppt/index.html"]
        formats = (
            getattr(ctx.config.delivery, "formats", [])
            if hasattr(ctx, "config") and hasattr(ctx.config, "delivery")
            else []
        )
        if "pptx" in formats:
            artifacts.append("output/ppt/presentation.pptx")
        return artifacts
