"""Stage S6: PPT Generation.

Uses the DashiPPTBridge to convert the S5 report into an HTML-based
slide presentation with theme support.
"""

from __future__ import annotations

from anappt.bridge.dashi_ppt import DashiPPTBridge
from anappt.i18n import t
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput


class S6PPTStage(StageBase):
    """Stage S6: PPT Generation.

    Reads the S5 report markdown and uses the DashiPPTBridge to generate
    an HTML slide presentation. The user can select a theme during this
    stage if the UI is available.
    """

    stage_id: str = "S6"
    stage_name: str = "stage.s6.name"

    def run(self, ctx: PipelineContext) -> StageOutput:
        """Execute the PPT generation stage.

        Args:
            ctx: Pipeline context.

        Returns:
            StageOutput with the generated PPT file path.
        """
        self._log_ui(ctx, t("s6.generating_ppt"))

        # Read S5 report
        report_path = ctx.get_artifact_path("report.md")
        if not report_path.exists():
            return StageOutput(
                success=False,
                summary="Report not found. Please run S5 first.",
                next_action="retry",
            )
        report_content = report_path.read_text(encoding="utf-8")

        # Determine theme
        theme = "default"
        config_theme = ctx.config.delivery.theme_preference
        if config_theme and config_theme in DashiPPTBridge.list_themes():
            theme = config_theme
        elif ctx.ui is not None:
            # Ask user to select theme
            themes = DashiPPTBridge.list_themes()
            self._log_ui(ctx, t("s6.selecting_theme"))
            headers = ["#", "Theme", "Description"]
            rows = [[str(i + 1), name, desc] for i, (name, desc) in enumerate(themes.items())]
            ctx.ui.table(headers, rows)
            choice = ctx.ui.input(">")
            try:
                idx = int(choice.strip()) - 1
                theme = list(themes.keys())[idx]
            except (ValueError, IndexError):
                theme = "default"

        # Create bridge and generate PPT
        ppt_dir = ctx.get_artifact_path("ppt")
        bridge = DashiPPTBridge(output_dir=ppt_dir, theme=theme)

        try:
            html_path = bridge.generate_ppt(
                markdown_content=report_content,
                theme=theme,
                title=ctx.config.project.name or "Analysis Report",
                filename="presentation.html",
            )
        except ValueError as e:
            return StageOutput(
                success=False,
                summary=str(e),
                next_action="retry",
            )
        except Exception as e:
            return StageOutput(
                success=False,
                summary=f"PPT generation failed: {e}",
                next_action="retry",
            )

        # Log to session
        self._log_session(ctx, t("bridge.ppt_generated", path=str(html_path)))

        self._log_ui(ctx, t("s6.ppt_generated", path=str(html_path)))

        return StageOutput(
            success=True,
            artifacts=[str(html_path.relative_to(ctx.project_dir))],
            summary=t("s6.ppt_generated", path=str(html_path)),
            data={
                "ppt_path": str(html_path),
                "theme": theme,
            },
            next_action="confirm",
        )

    def get_artifacts(self, ctx: PipelineContext) -> list[str]:
        """Return the artifact paths for this stage.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing the presentation.html path.
        """
        return ["output/ppt/presentation.html"]
