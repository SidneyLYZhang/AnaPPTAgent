"""Stage S4: Data Analysis.

Uses the analysis LLM with the AgentLoop tool-calling framework to
perform data analysis. The agent can call code execution, web search,
and web fetch tools to explore and analyze the loaded data.

Declarative interface (used by the conversation-driven TUI):
    - goal: ``s4.goal`` — iteratively perform deep analysis and produce
      ``.anappt/s4_analysis_report.md``, supporting multiple rounds of
      user feedback.
    - artifacts: ``.anappt/s4_analysis_report.md``.
    - system_prompt_fragment: Chinese guidance per design 4.4 — read
      ``report.yaml`` + ``data/`` + ``.anappt/s2_data_requirement.md``,
      run an iterative analysis loop (preliminary analysis → on-demand
      ``execute_python``/``search_web``/``fetch_url`` → integrate
      conclusions → output the report), accept user feedback to deepen
      analysis and update the report, optionally generate charts to
      ``output/images/``, write the artifact and await user ``confirm``.
    - tools: ``read_file``/``write_artifact``/``execute_python``/
      ``search_web``/``fetch_url``/``read_memory``/``read_history``.
    - is_ready: ``.anappt/s4_analysis_report.md`` exists and is non-empty.

The legacy ``run()`` method is preserved for backward compatibility with
the Orchestrator-based execution path; it will be removed once the
conversation runner is fully wired (Task C2-C4).
"""

from __future__ import annotations

import json

from anappt.i18n import t
from anappt.io.data_loader import load_all
from anappt.stage_base import StageBase
from anappt.tools.agent_loop import AgentLoop, ToolDef
from anappt.types import PipelineContext, StageOutput

# Stage-specific system prompt fragment (Chinese, drives S4 conversation).
# S4 is the core analysis stage with an iterative loop and the broadest
# tool subset (code exec + web search + web fetch).
S4_SYSTEM_PROMPT_FRAGMENT = """\
你当前处于 S4「数据分析」阶段,这是整个流水线中最重要的阶段,支持迭代循环。
你的目标是基于数据进行深度分析,产出 ``.anappt/s4_analysis_report.md``,
并支持用户多轮反馈直至满意。

请按以下迭代流程驱动对话：

1. 用 ``read_file`` 读取上下文：
   - ``report.yaml`` 获取分析目标、受众、成功标准
   - ``data/`` 下数据文件(若需要可先 ``execute_python`` 扫描查看结构)
   - ``.anappt/s2_data_requirement.md`` 获取分析维度参考
   - ``.anappt/s3_data_profile.md`` 获取数据 profile(若已生成)
2. 进行初步分析推理,形成第一版结论草案。
3. 按需调用工具进行迭代补充(可多轮):
   - ``execute_python``:统计计算、数据透视、关联分析、按需生成图表至
     ``output/images/``(S4 不强制生成图表;若用户要求或分析需要再生成)
   - ``search_web``:补充行业背景、竞品数据、市场报告
   - ``fetch_url``:读取相关网页/报告/政策文件全文
     (若 ``fetch_url`` 工具不可用——例如未配置 JINA_API_KEY——请明确告知用户
     并改用 ``search_web`` 提供的摘要)
4. 整合分析结论 → 写入 ``.anappt/s4_analysis_report.md`` 草案。
   报告以数据列表与文字结论为主,为后续 PPT 编辑留出灵活性。
5. 提示用户复核草案并提供反馈。
6. 接收用户反馈 → 深度推理补充 → 更新报告 → 再次提交用户确认。
7. 循环直到用户满意,明确确认"分析结论无误,可以进入报告撰写"后输入 ``confirm``。

写报告时调用 ``write_artifact(".anappt/s4_analysis_report.md", <内容>)``
(可多次覆盖更新),使用清晰的 Markdown 结构(如执行摘要、方法、关键发现、
详细分析、建议等章节)。

在用户输入 ``confirm`` 前,你不可自行推进阶段。你不可调用本阶段未授权的工具
(如 ``render_deck``/``export_pptx`` 等)。"""


class S4AnalysisStage(StageBase):
    """Stage S4: Data Analysis.

    Creates an agent loop with tools (code execution, web search, web fetch)
    and uses the analysis model to perform data analysis on the loaded data.
    The output is a structured analysis report in Markdown.
    """

    stage_id: str = "S4"
    stage_name: str = "stage.s4.name"
    goal: str = "s4.goal"

    def _build_tools(self, ctx: PipelineContext) -> tuple[dict, list[ToolDef]]:
        """Build the tool dictionary and definitions for the agent loop.

        Args:
            ctx: Pipeline context.

        Returns:
            Tuple of (tools dict, tool_defs list).
        """
        from anappt.tools.code_exec import execute_python
        from anappt.tools.web_fetch import fetch_url
        from anappt.tools.web_fetch import is_available as fetch_available
        from anappt.tools.web_search import search_web

        data_dir = ctx.get_data_dir()

        tools: dict = {
            "execute_python": lambda code: execute_python(
                code, timeout=60, allowed_dirs=[str(data_dir)]
            ).model_dump(),
            "search_web": lambda query, num_results=5: [
                r.model_dump() for r in search_web(query, num_results)
            ],
        }

        tool_defs: list[ToolDef] = [
            ToolDef(
                name="execute_python",
                description="Execute Python code in a sandbox. Returns stdout, stderr, returncode.",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute",
                        },
                    },
                    "required": ["code"],
                },
            ),
            ToolDef(
                name="search_web",
                description=(
                    "Search the web for information. "
                    "Returns list of results with title, url, snippet."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Max results (default 5)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            ),
        ]

        # Add web_fetch if available
        if fetch_available():
            tools["fetch_url"] = fetch_url
            tool_defs.append(
                ToolDef(
                    name="fetch_url",
                    description=(
                        "Fetch and read the content of a web page. "
                        "Returns markdown content."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to fetch",
                            },
                        },
                        "required": ["url"],
                    },
                )
            )

        return tools, tool_defs

    def run(self, ctx: PipelineContext) -> StageOutput:
        """Execute the data analysis stage.

        Args:
            ctx: Pipeline context.

        Returns:
            StageOutput with the analysis report.
        """
        self._log_ui(ctx, t("s4.analyzing"))

        # Read S1 and S2 outputs for context
        s1_path = ctx.get_anappt_path("s1_topic.md")
        s2_path = ctx.get_anappt_path("s2_data_requirement.md")
        s1_content = s1_path.read_text(encoding="utf-8") if s1_path.exists() else ""
        s2_content = s2_path.read_text(encoding="utf-8") if s2_path.exists() else ""

        # Load data for context
        data_dir = ctx.get_data_dir()
        dataframes = load_all(data_dir) if data_dir.exists() else {}

        # Build data summary for the LLM
        data_summary: list[str] = []
        for name, df in dataframes.items():
            data_summary.append(
                f"- {name}: {df.shape[0]} rows, {df.shape[1]} columns, "
                f"columns={df.columns.tolist()}"
            )
        data_summary_str = "\n".join(data_summary) if data_summary else "No data files loaded."

        # Write data to a temp location for code execution
        data_info_path = ctx.get_anappt_path("data_info.json")
        data_info: dict = {}
        for name, df in dataframes.items():
            data_info[name] = {
                "rows": int(df.shape[0]),
                "cols": int(df.shape[1]),
                "columns": df.columns.tolist(),
                "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            }
        data_json = json.dumps(data_info, ensure_ascii=False, indent=2)
        data_info_path.write_text(data_json, encoding="utf-8")

        # Build tools
        tools, tool_defs = self._build_tools(ctx)

        # Create agent loop
        agent = AgentLoop(
            llm=ctx.llm,
            role="analysis",
            tools=tools,
            tool_defs=tool_defs,
            max_iterations=10,
        )

        system_prompt = (
            "You are an expert data analyst. Your task is to perform thorough data analysis "
            "based on the analysis topic and data requirements. Use the available tools to: "
            "(1) Load and explore the data files, (2) Perform statistical analysis, "
            "(3) Create visualizations if needed, (4) Identify key insights and patterns. "
            "Output a comprehensive analysis report in Markdown with sections for: "
            "Executive Summary, Methodology, Key Findings, Detailed Analysis, and Recommendations. "
            "Write in the same language as the project."
        )

        user_message = (
            f"## Analysis Topic\n\n{s1_content}\n\n"
            f"## Data Requirements\n\n{s2_content}\n\n"
            f"## Available Data\n{data_summary_str}\n"
            f"Data directory: {data_dir}\n"
        )

        try:
            response = agent.run(system_prompt, user_message)
        except Exception as e:
            return StageOutput(
                success=False,
                summary=f"Analysis failed: {e}",
                next_action="retry",
            )

        # Write output artifact
        artifact_path = ctx.get_anappt_path("s4_analysis_report.md")
        artifact_path.write_text(response, encoding="utf-8")

        # Log to session
        self._log_session(ctx, response)

        self._log_ui(ctx, t("s4.analysis_complete"))

        return StageOutput(
            success=True,
            artifacts=[str(artifact_path.relative_to(ctx.project_dir))],
            summary=response[:200] + "..." if len(response) > 200 else response,
            data={"data_tables": list(dataframes.keys())},
            next_action="confirm",
        )

    def get_artifacts(self, ctx: PipelineContext) -> list[str]:
        """Return the artifact paths for this stage.

        Per design 4.4, S4 produces ``.anappt/s4_analysis_report.md``.

        Args:
            ctx: Pipeline context.

        Returns:
            List containing the s4_analysis_report.md path.
        """
        return [".anappt/s4_analysis_report.md"]

    def system_prompt_fragment(self, ctx: PipelineContext) -> str:
        """Return the S4-specific system prompt fragment.

        Drives the LLM to read ``report.yaml`` + ``data/`` + S2/S3 artifacts,
        run an iterative analysis loop with code exec / web search / web fetch,
        write the artifact and await user ``confirm``.

        Args:
            ctx: Pipeline context.

        Returns:
            Chinese system prompt fragment for S4.
        """
        return S4_SYSTEM_PROMPT_FRAGMENT

    def tools(self, ctx: PipelineContext) -> list[str]:
        """Return the subset of tools the LLM may use in S4.

        Args:
            ctx: Pipeline context.

        Returns:
            List of enabled tool names for S4.
        """
        return [
            "read_file",
            "write_artifact",
            "execute_python",
            "search_web",
            "fetch_url",
            "read_memory",
            "read_history",
        ]

    def is_ready(self, ctx: PipelineContext) -> bool:
        """Check whether S4's expected artifact is ready.

        Returns True only when ``.anappt/s4_analysis_report.md`` exists
        and is non-empty.

        Args:
            ctx: Pipeline context.

        Returns:
            True if the artifact exists and is non-empty.
        """
        artifact_path = ctx.project_dir / ".anappt" / "s4_analysis_report.md"
        if not artifact_path.exists():
            return False
        if not artifact_path.is_file():
            return False
        try:
            content = artifact_path.read_text(encoding="utf-8")
        except OSError:
            return False
        return bool(content.strip())
