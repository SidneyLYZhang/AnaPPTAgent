"""Stage S5: Report Generation.

Uses the writing LLM to transform the S4 analysis report into a
polished, well-structured analysis report in Markdown format.

Declarative interface (used by the conversation-driven TUI):
    - goal: ``s5.goal`` — organize analysis conclusions into a deliverable
      report with standard structure and produce ``output/final_report.md``.
    - artifacts: ``output/final_report.md``.
    - system_prompt_fragment: Chinese guidance per design 4.5 — read
      ``report.yaml`` + ``.anappt/s4_analysis_report.md`` + optional
      ``output/images/``, generate the report with the standard structure
      (summary / background & objectives / data sources & methodology /
      core findings (multi-section) / conclusions & recommendations /
      appendix), write the artifact, remind the user to open and review
      the file, and await user ``confirm``.
    - tools: ``read_file``/``write_artifact``/``read_memory``/``read_history``.
    - is_ready: ``output/final_report.md`` exists, is non-empty, and
      contains at least 2 level-1 headings (``# ``).

The legacy ``run()`` method is preserved for backward compatibility with
the Orchestrator-based execution path (it still writes ``output/report.md``
and ``.anappt/s5_report.md``); it will be removed once the conversation
runner is fully wired (Task C2-C4).
"""

from __future__ import annotations

from anappt.i18n import t
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput

# Stage-specific system prompt fragment (Chinese, drives S5 conversation).
# S5 is a writing stage that produces the final deliverable report.
S5_SYSTEM_PROMPT_FRAGMENT = """\
你当前处于 S5「报告生成」阶段。
你的目标是将分析结论组织为完整、可交付的分析报告,
并写入 ``output/final_report.md``。

请按以下流程驱动对话：

1. 用 ``read_file`` 读取上下文：
   - ``report.yaml`` 获取选题、受众、目标、成功标准
   - ``.anappt/s4_analysis_report.md`` 获取已确认的分析结论
   - ``output/images/`` 下的图表文件清单(可选,若 S4 生成了图表)
2. 按标准报告结构生成完整报告,至少包含以下章节：
   - 摘要 / Executive Summary
   - 背景与目标
   - 数据来源与方法
   - 核心发现(可按主题拆为多个子章节)
   - 结论与建议
   - 附录 / 数据说明
3. 调用 ``write_artifact("output/final_report.md", <内容>)`` 写入报告,
   使用清晰的 Markdown 格式(标题、表格、列表、图片引用等)。
4. 写完后**明确提醒用户打开 ``output/final_report.md`` 查看和修改**,
   告知用户可以：
   - 直接用编辑器打开文件自行修改,改完后回到对话输入 ``confirm``
   - 或直接在对话中提出修改意见,由你更新报告后再请用户确认
5. 用户可多次往返修改,直到满意为止。用户明确确认"报告内容无误"后
   输入 ``confirm`` 推进至 S6。

在用户输入 ``confirm`` 前,你不可自行推进阶段。如用户提出修改意见
(如调整章节结构、补充结论、修改措辞),根据反馈更新产出物后再次请用户确认。
你不可调用本阶段未授权的工具(如 ``execute_python``/``search_web``/``fetch_url``/
``render_deck``/``export_pptx`` 等)。"""


class S5ReportStage(StageBase):
    """Stage S5: Report Generation.

    Takes the S4 analysis report and produces a polished, reader-friendly
    analysis report. The output is written to output/report.md and
    the user is prompted to review it before proceeding to PPT generation.
    """

    stage_id: str = "S5"
    stage_name: str = "stage.s5.name"
    goal: str = "s5.goal"

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

        Per design 4.5, S5 (declarative) produces ``output/final_report.md``.
        The legacy ``run()`` still writes ``output/report.md`` and
        ``.anappt/s5_report.md``; this method returns the declarative
        artifact path consumed by the conversation runner.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing the final_report.md path.
        """
        return ["output/final_report.md"]

    def system_prompt_fragment(self, ctx: PipelineContext) -> str:
        """Return the S5-specific system prompt fragment.

        Drives the LLM to read ``report.yaml`` + S4 analysis report + optional
        images, generate the report with the standard structure, write the
        artifact, remind the user to open and review the file, and await
        user ``confirm``.

        Args:
            ctx: Pipeline context.

        Returns:
            Chinese system prompt fragment for S5.
        """
        return S5_SYSTEM_PROMPT_FRAGMENT

    def tools(self, ctx: PipelineContext) -> list[str]:
        """Return the subset of tools the LLM may use in S5.

        Args:
            ctx: Pipeline context.

        Returns:
            List of enabled tool names for S5.
        """
        return ["read_file", "write_artifact", "read_memory", "read_history"]

    def is_ready(self, ctx: PipelineContext) -> bool:
        """Check whether S5's expected artifact is ready.

        Returns True only when ``output/final_report.md`` exists, is
        non-empty, and contains at least 2 level-1 headings (lines
        starting with ``#`` followed by a space, i.e. ``# Title``).

        Args:
            ctx: Pipeline context.

        Returns:
            True if the artifact exists with sufficient structure.
        """
        artifact_path = ctx.project_dir / "output" / "final_report.md"
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
        # Per spec B6: content must contain at least 2 level-1 headings.
        h1_count = 0
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                h1_count += 1
                if h1_count >= 2:
                    return True
        return False
