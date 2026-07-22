"""Stage S2: Data Requirement Analysis.

Uses the reasoning LLM to analyze the S1 topic output and determine
what data is needed for the analysis, including schema requirements
and data source suggestions.

Declarative interface (used by the conversation-driven TUI):
    - goal: ``s2.goal`` — derive the data requirement list needed to
      complete the analysis from ``report.yaml`` and produce
      ``.anappt/s2_data_requirement.md``.
    - artifacts: ``.anappt/s2_data_requirement.md``.
    - system_prompt_fragment: Chinese guidance per design 4.2 — read
      ``report.yaml`` + ``.anappt/s1_topic.md`` + ``data/`` notes,
      derive the data requirement list (metrics/calculations, dimensions,
      time range, granularity, estimated volume, sources) purely from
      analysis needs (do NOT check whether the data exists), then write
      the artifact and wait for user ``confirm``.
    - tools: ``read_file``/``write_artifact``/``read_memory``/``read_history``.
    - is_ready: ``.anappt/s2_data_requirement.md`` exists and contains at
      least one heading or list item.

The legacy ``run()`` method is preserved for backward compatibility with
the Orchestrator-based execution path; it will be removed once the
conversation runner is fully wired (Task C2-C4).
"""

from __future__ import annotations

import json

from anappt.i18n import t
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput

# Stage-specific system prompt fragment (Chinese, drives S2 conversation).
# This is system-prompt text, not a user-visible UI string, so it is kept
# as a module-level constant rather than going through i18n ``t()``.
S2_SYSTEM_PROMPT_FRAGMENT = """\
你当前处于 S2「数据需求分析」阶段。
你的目标是基于报告规格书 ``report.yaml`` 与 S1 细化选题文档推导完成分析所需的
数据需求清单，并写入 ``.anappt/s2_data_requirement.md``。

请按以下流程驱动对话：

1. 调用 ``read_file("report.yaml")`` 读取报告选题、动机、受众、目标、成功标准，
   并调用 ``read_file(".anappt/s1_topic.md")`` 读取 S1 细化选题文档，
   作为推导数据需求的依据。
2. 如 ``data/`` 目录下存在用户提供的埋点文档、表结构说明、数据字典等说明文档
   （如 ``data/README.md``、``data/schema.md`` 等），用 ``read_file`` 读取作为参考；
   如不存在，则纯从分析需求出发推导，不强制要求。
3. 推理分析：要回答报告中的问题，需要哪些数据？逐项列出数据需求清单，
   每项至少包含：
   - 指标名称与计算口径（如 DAU=去重活跃用户数；ARPU=日收入/DAU）
   - 需要的维度拆分（如日期、渠道、新老用户、地域等）
   - 数据时间范围（与报告主题对应）
   - 最低数据粒度（日级别 / 小时级别 / 事件级别）
   - 预估数据量级（行数粗估）
   - 数据来源（埋点表 / 业务库 / 第三方 / 财务系统等）
4. **不检查数据是否实际存在**——纯粹从分析需求出发，即使 ``data/`` 为空也照常产出。
5. 调用 ``write_artifact(".anappt/s2_data_requirement.md", <内容>)`` 写入清单，
   使用清晰的 Markdown 结构（每类数据一个章节，按上述字段组织）。
6. 写完后明确提示用户通读 ``.anappt/s2_data_requirement.md``，
   并告知确认无误后输入 ``confirm`` 元命令推进；用户也可在此阶段离开去准备数据。

在用户输入 ``confirm`` 前，你不可自行推进阶段。如用户提出修改意见
（如增加指标、调整时间范围、补充来源），根据反馈更新产出物后再次请用户确认。
你不可调用本阶段未授权的工具（如 ``execute_python``/``search_web``/``fetch_url``/
``render_deck``/``export_pptx`` 等）。"""


class S2DataRequirementStage(StageBase):
    """Stage S2: Data Requirement Analysis.

    Reads the S1 topic document and produces a data requirement
    specification that describes what data is needed, expected schemas,
    and suggested data sources.
    """

    stage_id: str = "S2"
    stage_name: str = "stage.s2.name"
    goal: str = "s2.goal"

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

        Per design 4.2, S2 produces ``.anappt/s2_data_requirement.md``.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing the s2_data_requirement.md path.
        """
        return [".anappt/s2_data_requirement.md"]

    def system_prompt_fragment(self, ctx: PipelineContext) -> str:
        """Return the S2-specific system prompt fragment.

        Drives the LLM to read ``report.yaml`` + ``data/`` notes, derive the
        data requirement list (purely from analysis needs, without checking
        whether the data exists), write the artifact and await user ``confirm``.

        Args:
            ctx: Pipeline context.

        Returns:
            Chinese system prompt fragment for S2.
        """
        return S2_SYSTEM_PROMPT_FRAGMENT

    def tools(self, ctx: PipelineContext) -> list[str]:
        """Return the subset of tools the LLM may use in S2.

        Args:
            ctx: Pipeline context.

        Returns:
            List of enabled tool names for S2.
        """
        return ["read_file", "write_artifact", "read_memory", "read_history"]

    def is_ready(self, ctx: PipelineContext) -> bool:
        """Check whether S2's expected artifact is ready.

        Returns True only when ``.anappt/s2_data_requirement.md`` exists
        and contains at least one requirement entry or subheading (a
        Markdown heading line starting with ``#`` or a list item line
        starting with ``-`` / ``*``).

        Args:
            ctx: Pipeline context.

        Returns:
            True if the artifact exists with structured content.
        """
        artifact_path = ctx.project_dir / ".anappt" / "s2_data_requirement.md"
        if not artifact_path.exists():
            return False
        if not artifact_path.is_file():
            return False
        try:
            content = artifact_path.read_text(encoding="utf-8")
        except OSError:
            return False
        if not content.strip():
            return False
        # Per spec B3: content must contain at least one requirement entry
        # or subheading (Markdown heading '#' or list item '-'/'+').
        for line in content.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith(("-", "*")):
                return True
        return False
