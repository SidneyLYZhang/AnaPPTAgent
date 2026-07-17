"""Stage S4: Data Analysis.

Uses the analysis LLM with the AgentLoop tool-calling framework to
perform data analysis. The agent can call code execution, web search,
and web fetch tools to explore and analyze the loaded data.
"""

from __future__ import annotations

import json

from anappt.i18n import t
from anappt.io.data_loader import load_all
from anappt.stage_base import StageBase
from anappt.tools.agent_loop import AgentLoop, ToolDef
from anappt.types import PipelineContext, StageOutput


class S4AnalysisStage(StageBase):
    """Stage S4: Data Analysis.

    Creates an agent loop with tools (code execution, web search, web fetch)
    and uses the analysis model to perform data analysis on the loaded data.
    The output is a structured analysis report in Markdown.
    """

    stage_id: str = "S4"
    stage_name: str = "stage.s4.name"

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

        Args:
            ctx: Pipeline context.

        Returns:
            List containing the s4_analysis_report.md path.
        """
        return [".anappt/s4_analysis_report.md"]
