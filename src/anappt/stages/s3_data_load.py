"""Stage S3: Data Loading & Validation.

Loads all data files from the data/ directory, validates their schema
against the S2 requirements, and produces a data profile summary.
No LLM is needed for this stage — it uses the data_loader module.

Declarative interface (used by the conversation-driven TUI):
    - goal: ``s3.goal`` — load data, generate a data profile, check
      coverage against the S2 requirement, and write
      ``.anappt/s3_data_profile.md``.
    - artifacts: ``.anappt/s3_data_profile.md``.
    - system_prompt_fragment: Chinese guidance per design 4.3 — use
      ``execute_python`` to scan ``data/``, load and generate a profile
      (rows/cols/dtypes/null-rate; numeric min/max/mean/median/std;
      categorical unique counts + top values; datetime ranges), check
      coverage against S2 requirements, prompt the user for missing
      data if coverage is insufficient, write the artifact and wait for
      user ``confirm``.
    - tools: ``read_file``/``write_artifact``/``execute_python``/
      ``read_memory``/``read_history``.
    - is_ready: ``.anappt/s3_data_profile.md`` exists and is non-empty.

The legacy ``run()`` method (pure data processing, no LLM) is preserved
for backward compatibility with the Orchestrator-based execution path;
it will be removed once the conversation runner is fully wired
(Task C2-C4).
"""

from __future__ import annotations

from anappt.i18n import t
from anappt.io.data_loader import detect_files, get_file_info, load_all
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput

# Stage-specific system prompt fragment (Chinese, drives S3 conversation).
# S3 historically has no LLM in its legacy run(); in the conversation-driven
# model the LLM orchestrates execute_python calls to perform the same data
# processing and write the profile artifact.
S3_SYSTEM_PROMPT_FRAGMENT = """\
你当前处于 S3「数据加载与验证」阶段。
你的目标是加载用户提供的数据、生成数据 profile、对照 S2 需求检查覆盖度，
并写入 ``.anappt/s3_data_profile.md``。

请按以下流程驱动对话：

1. 用 ``execute_python`` 调用 pandas/polars/duckdb 扫描 ``data/`` 目录，
   自动识别文件格式（CSV / Excel / Parquet / SQLite / JSON 等）并加载。
   若 ``data/`` 为空或不存在，告知用户需要先准备数据再回到此阶段。
2. 对每个文件/表生成数据 profile，至少包含：
   - 基本结构：行数、列数、列名、列类型（dtype）
   - 空值率：每列空值数与空值率
   - 数值列统计：min / max / mean / median / std
   - 分类列统计：unique 值数量、top 值（含频次）
   - 日期列统计：时间范围（min/max 时刻）
3. 调用 ``read_file(".anappt/s2_data_requirement.md")`` 读取 S2 数据需求清单，
   对照需求逐项检查覆盖度（哪些指标可计算、哪些维度可拆分、时间范围是否覆盖），
   并在 profile 中明确标注覆盖度结论（完全覆盖 / 部分覆盖 / 未覆盖项清单）。
4. 若覆盖率不足，请明确提示用户补充哪些数据，并允许用户去准备数据后再次驱动扫描；
   也可建议用户回到 S2 调整需求清单。
5. 调用 ``write_artifact(".anappt/s3_data_profile.md", <内容>)`` 写入 profile 文档，
   使用清晰的 Markdown 结构（每个文件/表一个章节，按上述字段组织，附覆盖度小节）。
6. 写完后明确提示用户通读 ``.anappt/s3_data_profile.md``，
   并告知确认数据就绪后输入 ``confirm`` 元命令推进。

在用户输入 ``confirm`` 前，你不可自行推进阶段。如用户提出修改意见
（如补充数据后重新生成 profile、调整统计口径），根据反馈更新产出物后再次请用户确认。
你不可调用本阶段未授权的工具（如 ``search_web``/``fetch_url``/
``render_deck``/``export_pptx`` 等）。"""


class S3DataLoadStage(StageBase):
    """Stage S3: Data Loading & Validation.

    Detects and loads all supported data files from the project's data/
    directory, generates a data profile summary including file info,
    schema (columns and types), and basic statistics.
    """

    stage_id: str = "S3"
    stage_name: str = "stage.s3.name"
    goal: str = "s3.goal"

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

        Per design 4.3, S3 produces ``.anappt/s3_data_profile.md``.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing the s3_data_profile.md path.
        """
        return [".anappt/s3_data_profile.md"]

    def system_prompt_fragment(self, ctx: PipelineContext) -> str:
        """Return the S3-specific system prompt fragment.

        Drives the LLM to use ``execute_python`` to scan/load ``data/``,
        generate a data profile, check coverage against the S2 requirement,
        write the artifact and await user ``confirm``.

        Args:
            ctx: Pipeline context.

        Returns:
            Chinese system prompt fragment for S3.
        """
        return S3_SYSTEM_PROMPT_FRAGMENT

    def tools(self, ctx: PipelineContext) -> list[str]:
        """Return the subset of tools the LLM may use in S3.

        Args:
            ctx: Pipeline context.

        Returns:
            List of enabled tool names for S3.
        """
        return [
            "read_file",
            "write_artifact",
            "execute_python",
            "read_memory",
            "read_history",
        ]

    def is_ready(self, ctx: PipelineContext) -> bool:
        """Check whether S3's expected artifact is ready.

        Returns True only when ``.anappt/s3_data_profile.md`` exists
        and is non-empty.

        Args:
            ctx: Pipeline context.

        Returns:
            True if the artifact exists and is non-empty.
        """
        artifact_path = ctx.project_dir / ".anappt" / "s3_data_profile.md"
        if not artifact_path.exists():
            return False
        if not artifact_path.is_file():
            return False
        try:
            content = artifact_path.read_text(encoding="utf-8")
        except OSError:
            return False
        return bool(content.strip())
