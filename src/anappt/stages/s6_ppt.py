"""Stage S6: PPT Generation.

Uses the DashiPPTBridge to convert the S5 report into an HTML-based
slide presentation with theme support.

Declarative interface (used by the conversation-driven TUI):
    - goal: ``s6.goal`` — build ``output/ppt/goal.json`` from
      ``output/final_report.md`` + ``report.yaml`` and render
      ``output/ppt/presentation.html``.
    - artifacts: ``output/ppt/goal.json`` and
      ``output/ppt/presentation.html``.
    - system_prompt_fragment: Chinese guidance per design 4.6 — read
      SKILL.md (path injected by ConversationRunner via ``skill_root``)
      + ``output/final_report.md`` + ``report.yaml``, ask the user to
      pick a ``themePack`` from theme01-theme12, construct
      ``output/ppt/goal.json`` (title/goal/audience/owner/randomSeed/
      pageCount/themePack/slides[] with concrete layout + full props),
      call ``render_deck`` to render ``output/ppt/presentation.html``,
      await user ``confirm`` after browser editing, and (if
      ``delivery.formats`` contains pptx) call ``export_pptx``.
    - tools: ``read_file``/``write_artifact``/``render_deck``/
      ``export_pptx``/``read_memory``/``update_memory``/``read_history``.
    - is_ready: both ``output/ppt/goal.json`` (parseable as JSON) and
      ``output/ppt/presentation.html`` exist.

The legacy ``run()`` method is preserved for backward compatibility with
the Orchestrator-based execution path; it will be removed once the
conversation runner is fully wired (Task C2-C4).
"""

from __future__ import annotations

import json
from pathlib import Path

from anappt.bridge.dashi_ppt import DashiPPTBridge
from anappt.i18n import t
from anappt.stage_base import StageBase
from anappt.types import PipelineContext, StageOutput

# Stage-specific system prompt fragment (Chinese, drives S6 conversation).
# S6 reads the dashi-ppt SKILL.md (path provided by ConversationRunner
# via the skill_root context) and constructs goal.json, then renders the
# deck and (optionally) exports PPTX.
S6_SYSTEM_PROMPT_FRAGMENT = """\
你当前处于 S6「PPT 生成」阶段,这是流水线的最后一个阶段。
你的目标是基于 ``output/final_report.md`` 与 ``report.yaml`` 构造
``output/ppt/goal.json`` 并渲染 ``output/ppt/presentation.html``,
让用户在浏览器中编辑确认后推进。

dashi-ppt-skill 的 ``SKILL.md`` 路径由 ConversationRunner 通过
``skill_root`` 注入;请用 ``read_file`` 读取该 SKILL.md 作为你的工作流指令、
JSON 结构约定与可用版式(layout)清单的来源。

请按以下 7 步流程驱动对话：

1. **前置检查 skill**：确认 ``skill_root`` 已注入且 SKILL.md 可读;
   若未注入或不可读,告知用户需先运行 ``anappt setup`` 安装 dashi-ppt-skill,
   并中止 S6(不要尝试自行下载)。
2. **加载 SKILL.md**：用 ``read_file`` 读取 ``<skill_root>/SKILL.md``,
   获取工作流指令、goal.json 的 JSON 结构约定与可用版式清单。
3. **用户选择主题**：向用户展示 12 套主题(``theme01``–``theme12``,
   含简短预览说明),由用户选定本次 PPT 的 ``themePack``。
   若 ``report.yaml`` 的 ``delivery.theme_preference`` 已非空,可直接采用并告知用户。
4. **构造 goal.json**：用 ``read_file`` 读取 ``output/final_report.md`` 与
   ``report.yaml``,按 SKILL.md 的 JSON 结构构造 ``output/ppt/goal.json``,
   必须包含字段：``title / goal / audience / owner / randomSeed / pageCount /
   themePack / slides[]``;每页 ``slides[]`` 必须填具体 ``layout``
   (从 ``layout:query`` 候选选)和完整 ``props`` (覆写 ``copyKeys``),
   不可残留模板默认文案。然后调用 ``write_artifact("output/ppt/goal.json", <JSON>)`` 写入。
5. **渲染 HTML**：调用 ``render_deck`` 工具渲染
   ``output/ppt/presentation.html`` (工具参数由 ConversationRunner 桥接到
   dashi-ppt 的渲染脚本)。
6. **浏览器编辑确认**：告知用户在浏览器中浏览并编辑 PPT,满意后回到 CLI 输入
   ``confirm``;不满意可修订 ``goal.json`` 后回到第 5 步重渲。
7. **导出 PPTX(可选)**：若 ``report.yaml`` 的 ``delivery.formats`` 含 ``pptx``,
   在用户确认后调用 ``export_pptx`` 导出 ``output/ppt/presentation.pptx``。

在用户输入 ``confirm`` 前,你不可自行推进阶段。你不可调用本阶段未授权的工具
(如 ``execute_python``/``search_web``/``fetch_url`` 等)。"""


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
    goal: str = "s6.goal"

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

        Per design 4.6 and Task B7, S6 (declarative) produces
        ``output/ppt/goal.json`` and ``output/ppt/presentation.html``.
        The legacy ``run()`` writes ``output/ppt/ppt/index.html`` and
        optionally ``output/ppt/presentation.pptx``; this method returns
        the declarative artifact paths consumed by the conversation runner.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing goal.json and presentation.html paths.
        """
        return ["output/ppt/goal.json", "output/ppt/presentation.html"]

    def system_prompt_fragment(self, ctx: PipelineContext) -> str:
        """Return the S6-specific system prompt fragment.

        Drives the LLM to read SKILL.md (path injected by ConversationRunner
        via ``skill_root``) + ``output/final_report.md`` + ``report.yaml``,
        ask the user to pick a ``themePack``, construct ``goal.json``,
        call ``render_deck`` to render ``presentation.html``, await user
        ``confirm``, and (if pptx is requested) call ``export_pptx``.

        Args:
            ctx: Pipeline context.

        Returns:
            Chinese system prompt fragment for S6.
        """
        return S6_SYSTEM_PROMPT_FRAGMENT

    def tools(self, ctx: PipelineContext) -> list[str]:
        """Return the subset of tools the LLM may use in S6.

        Args:
            ctx: Pipeline context.

        Returns:
            List of enabled tool names for S6.
        """
        return [
            "read_file",
            "write_artifact",
            "render_deck",
            "export_pptx",
            "read_memory",
            "update_memory",
            "read_history",
        ]

    def is_ready(self, ctx: PipelineContext) -> bool:
        """Check whether S6's expected artifacts are ready.

        Returns True only when **both** ``output/ppt/goal.json`` and
        ``output/ppt/presentation.html`` exist, and ``goal.json`` can be
        parsed as valid JSON.

        Args:
            ctx: Pipeline context.

        Returns:
            True if both artifacts exist and goal.json is valid JSON.
        """
        project_dir = ctx.project_dir
        goal_json_path = project_dir / "output" / "ppt" / "goal.json"
        html_path = project_dir / "output" / "ppt" / "presentation.html"
        if not goal_json_path.exists():
            return False
        if not html_path.exists():
            return False
        try:
            json.loads(goal_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return True
