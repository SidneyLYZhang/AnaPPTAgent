"""Stage S1: Topic & Goal Definition.

Uses the reasoning LLM to analyze report.yaml and generate a refined
topic definition with clear objectives and success criteria.

Declarative interface (used by the conversation-driven TUI):
    - goal: ``s1.goal`` — collect topic/motivation/audience/objectives/
      success-criteria/delivery via conversation and produce
      ``report.yaml`` + ``.anappt/s1_topic.md``.
    - artifacts: ``report.yaml`` (project root) and ``.anappt/s1_topic.md``.
    - system_prompt_fragment: Chinese guidance for the LLM to drive the
      conversation per design 4.1.
    - tools: ``read_file``/``write_artifact``/``read_memory``/``read_history``.
    - is_ready: validates report.yaml parses and core fields are non-empty
      and s1_topic.md exists.

The legacy ``run()`` method is preserved for backward compatibility with
the Orchestrator-based execution path; it will be removed once the
conversation runner is fully wired (Task C2-C4).
"""

from __future__ import annotations

import json

from anappt.i18n import t
from anappt.io.config import ReportConfig
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput

# Stage-specific system prompt fragment (Chinese, drives S1 conversation).
# This is system-prompt text, not a user-visible UI string, so it is kept
# as a module-level constant rather than going through i18n ``t()``.
S1_SYSTEM_PROMPT_FRAGMENT = """\
你当前处于 S1「选题与目标定义」阶段。
你的目标是通过对话把用户的模糊需求转化为结构化的报告规格书 ``report.yaml``
以及细化选题文档 ``.anappt/s1_topic.md``。

请按以下顺序通过对话逐一收集信息，每收集一项都要向用户复述确认，遇到模糊处要追问，直到信息完整：

1. 报告选题：主题、背景与动机（为什么要做这份分析？要解决什么业务问题？）。
2. 目标受众：谁会看这份报告？（决策层 / 执行层 / 外部客户等，可多个）。
3. 报告目标：要支撑什么决策？要回答什么具体问题？
4. 成功标准：怎样的报告算「好」？（结论有数据支撑、建议可落地执行等）。
5. 交付形式：期望 PPT 页数（如 15-20）、是否需要 PDF/HTML 版本、主题偏好（可留空由 S6 再选）。
6. 可选周期标识：一次性 / 月度 / 季度。

收集完毕后，调用 ``write_artifact("report.yaml", <YAML>)`` 写入项目根目录的 ``report.yaml``，
YAML 结构必须严格遵循：

```yaml
project:
  name: <项目名称>
  type: one_time | monthly | quarterly   # 与用户描述的周期标识一致
  created: <YYYY-MM-DD>

report:
  topic: <报告选题>
  motivation: <动机与背景>
  audience:
    - <受众1>
    - <受众2>
  objectives:
    - <目标1>
    - <目标2>
  success_criteria:
    - <成功标准1>
    - <成功标准2>

delivery:
  ppt_pages: <如 "15-20">
  formats: ["pptx", "html"]
  theme_preference: null   # 留空，由 S6 选定
```

接着调用 ``write_artifact(".anappt/s1_topic.md", <内容>)`` 写入细化选题文档，
对选题背景、动机、目标受众、报告目标、成功标准、建议的分析思路做更详尽的展开，供下游 S2/S4 引用。

写完两个产出物后，请明确提示用户通读 ``report.yaml`` 与 ``.anappt/s1_topic.md``，
并告知确认无误后输入 ``confirm`` 元命令推进。
在用户输入 ``confirm`` 前，你不可自行推进阶段，必须等待用户的确认或修改意见。
如用户提出修改，根据反馈更新产出物后再次请用户确认。

你不可调用本阶段未授权的工具（如 ``render_deck``/``export_pptx``/``execute_python``/
``search_web``/``fetch_url`` 等）。"""


class S1TopicStage(StageBase):
    """Stage S1: Topic & Goal Definition.

    Reads the report configuration from report.yaml, uses the reasoning
    model to refine the topic, objectives, and success criteria, and
    writes the output to .anappt/s1_topic.md.
    """

    stage_id: str = "S1"
    stage_name: str = "stage.s1.name"
    goal: str = "s1.goal"

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
        """Return the artifact paths this stage produces.

        Per design 4.1, S1 produces both ``report.yaml`` (project root)
        and ``.anappt/s1_topic.md``.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing ``report.yaml`` and ``.anappt/s1_topic.md``.
        """
        return ["report.yaml", ".anappt/s1_topic.md"]

    def system_prompt_fragment(self, ctx: PipelineContext) -> str:
        """Return the S1-specific system prompt fragment.

        Drives the LLM to collect topic/motivation/audience/objectives/
        success-criteria/delivery via conversation and write report.yaml
        + s1_topic.md, then await user ``confirm``.

        Args:
            ctx: Pipeline context.

        Returns:
            Chinese system prompt fragment for S1.
        """
        return S1_SYSTEM_PROMPT_FRAGMENT

    def tools(self, ctx: PipelineContext) -> list[str]:
        """Return the subset of tools the LLM may use in S1.

        Args:
            ctx: Pipeline context.

        Returns:
            List of enabled tool names for S1.
        """
        return ["read_file", "write_artifact", "read_memory", "read_history"]

    def is_ready(self, ctx: PipelineContext) -> bool:
        """Check whether S1's expected artifacts are ready.

        Returns True only when all of the following hold:
            - ``report.yaml`` exists at the project root.
            - ``report.yaml`` parses successfully via ``ReportConfig.from_yaml``.
            - ``report.topic``, ``report.motivation`` and ``report.objectives``
              are all non-empty.
            - ``.anappt/s1_topic.md`` exists.

        Any failure (missing file, parse error, empty required field)
        returns ``False`` without raising.

        Args:
            ctx: Pipeline context.

        Returns:
            True if S1's artifacts are complete and consistent.
        """
        project_dir = ctx.project_dir
        report_yaml_path = project_dir / "report.yaml"
        if not report_yaml_path.exists():
            return False

        try:
            config = ReportConfig.from_yaml(report_yaml_path)
        except Exception:
            return False

        report = config.report
        if not report.topic:
            return False
        if not report.motivation:
            return False
        if not report.objectives:
            return False

        s1_topic_path = project_dir / ".anappt" / "s1_topic.md"
        if not s1_topic_path.exists():
            return False

        return True
