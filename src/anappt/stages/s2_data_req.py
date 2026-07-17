"""Stage S2: Data Requirement Analysis.

Uses the reasoning LLM to analyze the S1 topic output and determine
what data is needed for the analysis, including schema requirements
and data source suggestions.
"""

from __future__ import annotations

import json

from anappt.i18n import t
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput


class S2DataRequirementStage(StageBase):
    """Stage S2: Data Requirement Analysis.

    Reads the S1 topic document and produces a data requirement
    specification that describes what data is needed, expected schemas,
    and suggested data sources.
    """

    stage_id: str = "S2"
    stage_name: str = "stage.s2.name"

    def run(self, ctx: PipelineContext) -> StageOutput:
        """Execute the data requirement analysis stage.

        Args:
            ctx: Pipeline context.

        Returns:
            StageOutput with the generated data requirement document.
        """
        self._log_ui(ctx, t("s2.analyzing_requirements"))

        # Read S1 output
        s1_path = ctx.get_anappt_path("s1_topic.md")
        if not s1_path.exists():
            return StageOutput(
                success=False,
                summary="S1 output not found. Please run S1 first.",
                next_action="retry",
            )
        s1_content = s1_path.read_text(encoding="utf-8")

        # Read existing data files for context
        data_dir = ctx.get_data_dir()
        existing_files: list[str] = []
        if data_dir.exists():
            existing_files = [f.name for f in data_dir.iterdir() if f.is_file()]

        system_prompt = (
            "You are a data analyst expert. Based on the analysis topic and "
            "existing data files, produce a data requirement document with: "
            "(1) Required Data Tables, (2) Expected Schema for each table "
            "(column name, type, description), (3) Data Quality Requirements, "
            "and (4) Suggested Data Sources. "
            "Write in the same language as the project."
        )

        user_message = (
            f"## S1 Topic Document\n\n{s1_content}\n\n"
            f"## Existing Data Files\n{json.dumps(existing_files, ensure_ascii=False)}\n"
        )

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
        artifact_path = ctx.get_anappt_path("s2_data_requirement.md")
        artifact_path.write_text(response, encoding="utf-8")

        # Log to session
        self._log_session(ctx, response)

        self._log_ui(ctx, t("s2.requirements_generated"))

        return StageOutput(
            success=True,
            artifacts=[str(artifact_path.relative_to(ctx.project_dir))],
            summary=response[:200] + "..." if len(response) > 200 else response,
            data={"existing_files": existing_files},
            next_action="confirm",
        )

    def get_artifacts(self, ctx: PipelineContext) -> list[str]:
        """Return the artifact paths for this stage.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing the s2_data_requirement.md path.
        """
        return [".anappt/s2_data_requirement.md"]
