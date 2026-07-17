"""Stage S5: Report Generation.

Uses the writing LLM to transform the S4 analysis report into a
polished, well-structured analysis report in Markdown format.
"""

from __future__ import annotations

from anappt.i18n import t
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput


class S5ReportStage(StageBase):
    """Stage S5: Report Generation.

    Takes the S4 analysis report and produces a polished, reader-friendly
    analysis report. The output is written to output/report.md and
    the user is prompted to review it before proceeding to PPT generation.
    """

    stage_id: str = "S5"
    stage_name: str = "stage.s5.name"

    def run(self, ctx: PipelineContext) -> StageOutput:
        """Execute the report generation stage.

        Args:
            ctx: Pipeline context.

        Returns:
            StageOutput with the generated report.
        """
        self._log_ui(ctx, t("s5.generating_report"))

        # Read S4 analysis report
        s4_path = ctx.get_anappt_path("s4_analysis_report.md")
        if not s4_path.exists():
            return StageOutput(
                success=False,
                summary="S4 analysis report not found. Please run S4 first.",
                next_action="retry",
            )
        s4_content = s4_path.read_text(encoding="utf-8")

        # Read S1 for context
        s1_path = ctx.get_anappt_path("s1_topic.md")
        s1_content = s1_path.read_text(encoding="utf-8") if s1_path.exists() else ""

        config = ctx.config

        system_prompt = (
            "You are a professional report writer. Transform the raw analysis output "
            "into a polished, well-structured analysis report. The report should be "
            "clear, concise, and suitable for the target audience. "
            "Use proper Markdown formatting with headers, tables, and lists. "
            "Include: Executive Summary, Background, Methodology, Findings, "
            "Conclusions, and Recommendations. Write in the same language as the project."
        )

        audience = ", ".join(config.report.audience) if config.report.audience else "General"
        objectives = (
            ", ".join(config.report.objectives)
            if config.report.objectives
            else "Not specified"
        )
        user_message = (
            f"## Original Topic\n\n{s1_content}\n\n"
            f"## Analysis Report\n\n{s4_content}\n\n"
            f"## Report Configuration\n"
            f"Audience: {audience}\n"
            f"Objectives: {objectives}\n"
        )

        try:
            response = ctx.llm.chat("writing", [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ])
        except Exception as e:
            return StageOutput(
                success=False,
                summary=f"LLM call failed: {e}",
                next_action="retry",
            )

        # Write output artifact
        artifact_path = ctx.get_artifact_path("report.md")
        artifact_path.write_text(response, encoding="utf-8")

        # Also write a copy to .anappt for reference
        anappt_copy = ctx.get_anappt_path("s5_report.md")
        anappt_copy.write_text(response, encoding="utf-8")

        # Log to session
        self._log_session(ctx, response)

        # Prompt user to review
        self._log_ui(ctx, t("s5.remind_open_report", path=str(artifact_path)))
        self._log_ui(ctx, t("s5.remind_edit_or_chat"))

        return StageOutput(
            success=True,
            artifacts=[
                str(artifact_path.relative_to(ctx.project_dir)),
                str(anappt_copy.relative_to(ctx.project_dir)),
            ],
            summary=t("s5.report_generated", path=str(artifact_path)),
            data={"report_path": str(artifact_path)},
            next_action="confirm",
        )

    def get_artifacts(self, ctx: PipelineContext) -> list[str]:
        """Return the artifact paths for this stage.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing the report.md and s5_report.md paths.
        """
        return ["output/report.md", ".anappt/s5_report.md"]
