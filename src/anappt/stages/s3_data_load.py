"""Stage S3: Data Loading & Validation.

Loads all data files from the data/ directory, validates their schema
against the S2 requirements, and produces a data profile summary.
No LLM is needed for this stage — it uses the data_loader module.
"""

from __future__ import annotations

from anappt.i18n import t
from anappt.io.data_loader import detect_files, get_file_info, load_all
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput


class S3DataLoadStage(StageBase):
    """Stage S3: Data Loading & Validation.

    Detects and loads all supported data files from the project's data/
    directory, generates a data profile summary including file info,
    schema (columns and types), and basic statistics.
    """

    stage_id: str = "S3"
    stage_name: str = "stage.s3.name"

    def run(self, ctx: PipelineContext) -> StageOutput:
        """Execute the data loading stage.

        Args:
            ctx: Pipeline context.

        Returns:
            StageOutput with the data profile document.
        """
        self._log_ui(ctx, t("s3.loading_data"))

        data_dir = ctx.get_data_dir()
        files = detect_files(data_dir)

        if not files:
            self._log_ui(ctx, t("s3.no_data_found"))
            return StageOutput(
                success=False,
                summary=t("s3.no_data_found"),
                next_action="retry",
            )

        # Load all data files
        try:
            dataframes = load_all(data_dir)
        except Exception as e:
            return StageOutput(
                success=False,
                summary=f"Data loading failed: {e}",
                next_action="retry",
            )

        # Build data profile
        profile_lines: list[str] = []
        profile_lines.append("# Data Profile\n")
        profile_lines.append(f"**Total Files:** {len(files)}\n")

        for name, df in dataframes.items():
            profile_lines.append(f"\n## {name}\n")
            profile_lines.append(f"- **Shape:** {df.shape[0]} rows x {df.shape[1]} columns")
            profile_lines.append(f"- **Columns:** {', '.join(df.columns.tolist())}")
            profile_lines.append(f"- **Dtypes:**\n```\n{df.dtypes.to_string()}\n```")

            # Basic statistics for numeric columns
            numeric_df = df.select_dtypes(include=["number"])
            if not numeric_df.empty:
                stats = numeric_df.describe().to_string()
                profile_lines.append(f"- **Statistics:**\n```\n{stats}\n```")

            # Null counts
            null_counts = df.isnull().sum()
            if null_counts.any():
                null_info = null_counts[null_counts > 0].to_string()
                profile_lines.append(f"- **Null Counts:**\n```\n{null_info}\n```")

        # File info section
        profile_lines.append("\n## File Details\n")
        for f in files:
            info = get_file_info(f)
            profile_lines.append(
                f"- **{info['file_name']}**: format={info['format']}, "
                f"size={info['size_bytes']} bytes"
            )

        profile_content = "\n".join(profile_lines)

        # Write output artifact
        artifact_path = ctx.get_anappt_path("s3_data_profile.md")
        artifact_path.write_text(profile_content, encoding="utf-8")

        self._log_ui(ctx, t("s3.data_loaded", count=len(files)))

        # Store data summary in context data for later stages
        data_summary: dict[str, dict] = {}
        for name, df in dataframes.items():
            data_summary[name] = {
                "rows": int(df.shape[0]),
                "cols": int(df.shape[1]),
                "columns": df.columns.tolist(),
            }

        return StageOutput(
            success=True,
            artifacts=[str(artifact_path.relative_to(ctx.project_dir))],
            summary=t("s3.data_loaded", count=len(files)),
            data={
                "file_count": len(files),
                "tables": data_summary,
            },
            next_action="confirm",
        )

    def get_artifacts(self, ctx: PipelineContext) -> list[str]:
        """Return the artifact paths for this stage.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing the s3_data_profile.md path.
        """
        return [".anappt/s3_data_profile.md"]
