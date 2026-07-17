"""Stage S1: Topic & Goal Definition.

Uses the reasoning LLM to analyze report.yaml and generate a refined
topic definition with clear objectives and success criteria.
"""

from __future__ import annotations

import json

from anappt.i18n import t
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput


class S1TopicStage(StageBase):
    """Stage S1: Topic & Goal Definition.

    Reads the report configuration from report.yaml, uses the reasoning
    model to refine the topic, objectives, and success criteria, and
    writes the output to .anappt/s1_topic.md.
    """

    stage_id: str = "S1"
    stage_name: str = "stage.s1.name"

    def run(self, ctx: PipelineContext) -> StageOutput:
        """Execute the topic definition stage.

        Args:
            ctx: Pipeline context with config and LLM.

        Returns:
            StageOutput with the generated topic document.
        """
        self._log_ui(ctx, t("s1.generating_topic"))

        config = ctx.config

        # Build the prompt for the LLM
        report_info = config.report
        project_info = config.project

        system_prompt = (
            "You are an expert analyst helping define a clear analysis topic. "
            "Based on the project configuration, produce a structured topic document "
            "with: (1) Refined Topic, (2) Analysis Objectives, (3) Success Criteria, "
            "and (4) Suggested Approach. Write in the same language as the project name."
        )

        audience = ", ".join(report_info.audience) if report_info.audience else "Not specified"
        user_message = (
            f"Project Name: {project_info.name}\n"
            f"Topic: {report_info.topic}\n"
            f"Motivation: {report_info.motivation}\n"
            f"Audience: {audience}\n"
            f"Objectives: {json.dumps(report_info.objectives, ensure_ascii=False)}\n"
            f"Success Criteria: {json.dumps(report_info.success_criteria, ensure_ascii=False)}\n"
        )

        # Call LLM
        try:
            response = ctx.llm.chat("reasoning", [
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
        artifact_path = ctx.get_anappt_path("s1_topic.md")
        artifact_path.write_text(response, encoding="utf-8")

        # Log to session
        self._log_session(ctx, response)

        self._log_ui(ctx, t("s1.topic_generated"))

        return StageOutput(
            success=True,
            artifacts=[str(artifact_path.relative_to(ctx.project_dir))],
            summary=response[:200] + "..." if len(response) > 200 else response,
            data={"topic": report_info.topic},
            next_action="confirm",
        )

    def get_artifacts(self, ctx: PipelineContext) -> list[str]:
        """Return the artifact paths for this stage.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing the s1_topic.md path.
        """
        return [".anappt/s1_topic.md"]
